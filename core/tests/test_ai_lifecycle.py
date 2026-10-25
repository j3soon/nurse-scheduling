"""Adversarial run scheduling, cancellation and session snapshot orderings."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This test is mostly AI generated.

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from nurse_scheduling.ai.app import OWNER_COOKIE, SessionStore
from nurse_scheduling.ai.context import ABORTED_RESPONSE_HISTORY, SCHEDULE_CHANGED_EVENT
from nurse_scheduling.ai.history import ChatHistory
from nurse_scheduling.ai.lifecycle import SessionRuns
from nurse_scheduling.ai.provider import ProviderError, TextDelta
from nurse_scheduling.ai.session_event_stream import SessionEventStream
from nurse_scheduling.ai.sessions import _session_bytes
from nurse_scheduling.ai.transcript import AppEventEntry, AssistantMessage, UserMessage

from .ai_test_helper import base_schedule_payload, schedule_yaml
from .test_ai_basic import AI_AUTH_HEADERS, FakeProvider, create_test_app, make_settings


def test_setup_failure_releases_session_and_the_next_request_can_run(monkeypatch):
    async def exercise():
        provider = FakeProvider()
        app = create_test_app(settings=make_settings(), provider=provider)
        original = app.state.session_optimizer.latest_result_artifact

        async def fail(_session_id):
            raise RuntimeError("artifact setup failed")

        monkeypatch.setattr(app.state.session_optimizer, "latest_result_artifact", fail)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=AI_AUTH_HEADERS
        ) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            response = await client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
            assert "event: error" in response.text
            assert not app.state.runs.busy(session_id)
            session = app.state.session_store._sessions[session_id]
            assert not session.active
            assert provider.calls == []
            assert session.transcript == [
                UserMessage("Question"),
                AssistantMessage("", "error"),
                AppEventEntry(ABORTED_RESPONSE_HISTORY),
            ]
            monkeypatch.setattr(app.state.session_optimizer, "latest_result_artifact", original)
            response = await client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})
            assert "event: done" in response.text
            assert provider.calls[0][1:3] == [
                {"role": "user", "content": "Question"},
                {"role": "user", "content": ABORTED_RESPONSE_HISTORY},
            ]

    asyncio.run(exercise())


def test_retirement_cancels_the_owner_and_queued_followups_without_recreating_events():
    async def exercise():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Provider:
            async def stream_events(self, _messages, tools=None):
                try:
                    started.set()
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
                yield

        app = create_test_app(settings=make_settings(), provider=Provider())
        store = app.state.session_store
        session = store.create("owner", schedule_yaml())
        callback = app.state.session_optimizer._on_completion
        active = asyncio.create_task(callback(session.id, "Review the optimizer result.", None))
        await started.wait()
        queued = asyncio.create_task(callback(session.id, "Review the optimizer result.", None))
        await asyncio.sleep(0)
        session.expires_at = 0
        with pytest.raises(HTTPException):
            store.require_owned(session.id, "owner")
        await asyncio.gather(active, queued, return_exceptions=True)
        assert cancelled.is_set()
        assert not app.state.runs.busy(session.id)
        assert app.state.session_event_stream.events_after(session.id) == ()
        assert session.id not in app.state.session_event_stream._signals

    asyncio.run(exercise())


def test_cancelling_a_queued_turn_does_not_let_its_successor_overtake_the_owner():
    async def exercise():
        turns = SessionRuns()
        release = asyncio.Event()
        started = []

        async def first(_turn):
            started.append("first")
            await release.wait()

        async def queued(turn):
            started.append(turn.id)

        first_turn = turns.start("session", first)
        middle = turns.start("session", queued, background=True)
        last = turns.start("session", queued, background=True)
        await asyncio.sleep(0)
        middle.cancel()
        await middle.done
        await asyncio.sleep(0)
        assert started == ["first"]
        release.set()
        await last.wait()
        await first_turn.wait()
        assert started == ["first", last.id]
        assert not turns.busy("session")
        await turns.close()

    asyncio.run(exercise())


def test_stop_is_idempotent_through_cleanup_and_cancels_active_and_queued_runs():
    async def exercise():
        turns = SessionRuns()
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()
        queued_ran = False

        async def run(_turn):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        async def queued(_turn):
            nonlocal queued_ran
            queued_ran = True

        active = turns.start("session", run)
        waiting = turns.start("session", queued, background=True)
        await started.wait()
        turns.stop("session")
        await cleaning.wait()
        turns.stop("session")
        assert turns.busy("session")
        with pytest.raises(HTTPException) as conflict:
            turns.start("session", queued)
        assert conflict.value.status_code == 409
        release.set()
        await asyncio.gather(active.done, waiting.done)
        assert not queued_ran
        assert not turns.busy("session")
        # A later optimizer completion is a new operation and may wake the agent.
        await turns.start("session", queued, background=True).wait()
        assert queued_ran
        await turns.close()

    asyncio.run(exercise())


def test_shutdown_joins_cleanup_and_stops_accepting_runs():
    async def exercise():
        turns = SessionRuns()
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()

        async def run(_turn):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        turns.start("session", run)
        await started.wait()
        closing = asyncio.create_task(turns.close())
        await cleaning.wait()
        assert not closing.done()
        with pytest.raises(HTTPException) as unavailable:
            turns.start("other", run)
        assert unavailable.value.status_code == 503
        release.set()
        await closing
        assert turns._runs == {}

    asyncio.run(exercise())


def test_stale_turn_cannot_release_or_commit_over_its_successor():
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    old = store.begin(session.id, "owner")
    store.abort(session.id, old)
    new = store.begin(session.id, "owner")
    assert not store.finish(session.id, [UserMessage("old"), AssistantMessage("old")], snapshot=old).run_saved
    store.abort(session.id, old)
    assert session.snapshot is new
    assert store.finish(session.id, [UserMessage("new"), AssistantMessage("new")], snapshot=new).run_saved
    assert session.transcript == [UserMessage("new"), AssistantMessage("new")]


def _edited_schedule(description: str) -> str:
    payload = base_schedule_payload()
    payload["description"] = description
    return schedule_yaml(payload)


@pytest.mark.parametrize("ending", ["answer", "stop"])
def test_schedule_update_during_a_run_applies_after_the_run(ending):
    store = SessionStore(make_settings())
    original = schedule_yaml()
    session = store.create("owner", original)
    turn = store.begin(session.id, "owner")
    store.update_schedule(session.id, "owner", _edited_schedule("Discarded"))
    store.update_schedule(session.id, "owner", original)
    assert session.queued_schedule is None
    edited = _edited_schedule("Edited")
    store.update_schedule(session.id, "owner", edited)
    assert session.schedule_yaml == original
    if ending == "answer":
        assert store.finish(session.id, [UserMessage("question"), AssistantMessage("answer")], snapshot=turn).run_saved
    else:
        store.abort(session.id, turn)
    store.apply_queued_schedule(session.id)

    assert session.schedule_yaml == edited and session.queued_schedule is None
    run_entries = [UserMessage("question"), AssistantMessage("answer")] if ending == "answer" else []
    assert session.transcript == [*run_entries, AppEventEntry(SCHEDULE_CHANGED_EVENT)]
    assert store.retained_bytes == _session_bytes(session)


def test_a_run_schedule_replaces_an_update_queued_during_the_run():
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    turn = store.begin(session.id, "owner")
    store.update_schedule(session.id, "owner", _edited_schedule("Browser"))
    applied = _edited_schedule("Assistant")

    completion = store.finish(session.id, [UserMessage("question"), AssistantMessage("answer")], applied, snapshot=turn)
    assert completion.run_saved and completion.replaced_queued_schedule
    store.apply_queued_schedule(session.id)

    assert session.schedule_yaml == applied and session.queued_schedule is None
    assert session.transcript == [UserMessage("question"), AssistantMessage("answer")]


def test_restore_applies_a_schedule_update_queued_before_the_restart():
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    store.begin(session.id, "owner")
    edited = _edited_schedule("Edited")
    store.update_schedule(session.id, "owner", edited)
    owner, expires_at, state = store.recovery_state(session.id)

    restored = SessionStore(make_settings()).restore(
        session.id, owner, json.loads(json.dumps(state)), expires_at, entries=[], next_entry_seq=0
    )

    assert restored.schedule_yaml == edited and restored.queued_schedule is None
    assert restored.transcript == [AppEventEntry(SCHEDULE_CHANGED_EVENT)]


@pytest.mark.parametrize("background", [False, True], ids=["foreground", "background"])
def test_stop_during_history_start_waits_for_history_then_releases_the_session(monkeypatch, background):
    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()
        records = []

        async def write(_self, operation, *args, **_kwargs):
            if operation == "start_run":
                entered.set()
                await release.wait()
            if operation in {"start_run", "finish_run"}:
                records.append((operation, args))
            return True

        monkeypatch.setattr(ChatHistory, "write", write)
        provider = FakeProvider()
        app = create_test_app(settings=make_settings(history_postgres_url="test"), provider=provider)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=AI_AUTH_HEADERS
        ) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            if background:
                running = asyncio.create_task(
                    app.state.session_optimizer._on_completion(session_id, "Review the optimizer result.", None)
                )
            else:
                running = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "Ask"}))
            await entered.wait()
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            assert app.state.runs.busy(session_id)
            release.set()
            await asyncio.wait_for(asyncio.gather(running, return_exceptions=True), timeout=1)
            assert not app.state.runs.busy(session_id)
            assert not app.state.session_store._sessions[session_id].active
            assert provider.calls == []
            assert [operation for operation, _ in records] == ["start_run", "finish_run"]
            assert records[-1][1][1] == "cancelled"

    asyncio.run(exercise())


@pytest.mark.parametrize("failed", [False, True], ids=["completed", "failed"])
def test_terminal_background_event_is_published_only_after_history_cleanup(monkeypatch, failed):
    async def exercise():
        finalizing = asyncio.Event()
        release = asyncio.Event()
        records = []

        async def write(_self, operation, *_args, **_kwargs):
            if operation == "finish_run":
                finalizing.set()
                await release.wait()
            if operation in {"start_run", "finish_run"}:
                records.append(operation)
            return True

        monkeypatch.setattr(ChatHistory, "write", write)
        app = create_test_app(
            settings=make_settings(history_postgres_url="test"),
            provider=FakeProvider([[ProviderError("private failure")]]) if failed else FakeProvider(),
        )
        session = app.state.session_store.create("owner", schedule_yaml())
        running = asyncio.create_task(
            app.state.session_optimizer._on_completion(session.id, "Review the optimizer result.", None)
        )
        await finalizing.wait()
        assert app.state.runs.busy(session.id)
        assert not any(
            event.type in {"done", "error", "stopped", "stale"}
            for event in app.state.session_event_stream.events_after(session.id)
        )
        app.state.runs.stop(session.id)
        release.set()
        await running
        assert not app.state.runs.busy(session.id)
        terminals = [
            event.type
            for event in app.state.session_event_stream.events_after(session.id)
            if event.type in {"done", "error", "stopped", "stale"}
        ]
        assert terminals == ["error" if failed else "done"]
        assert records == ["start_run", "finish_run"]

    asyncio.run(exercise())


def test_stop_during_completed_history_write_keeps_completed_outcome(monkeypatch):
    async def exercise():
        finalizing = asyncio.Event()
        release = asyncio.Event()
        statuses = []

        async def write(_self, operation, *args, **_kwargs):
            if operation == "finish_run":
                finalizing.set()
                await release.wait()
                statuses.append(args[1])
            return True

        monkeypatch.setattr(ChatHistory, "write", write)
        app = create_test_app(settings=make_settings(history_postgres_url="test"), provider=FakeProvider())
        session = app.state.session_store.create("owner", schedule_yaml())
        running = asyncio.create_task(
            app.state.session_optimizer._on_completion(session.id, "Review the optimizer result.", None)
        )

        await asyncio.wait_for(finalizing.wait(), timeout=1)
        assert [type(entry) for entry in session.transcript] == [UserMessage, AssistantMessage]
        app.state.runs.stop(session.id)
        release.set()
        await asyncio.wait_for(running, timeout=1)

        assert statuses == ["completed"]
        assert [event.type for event in app.state.session_event_stream.events_after(session.id)][-1] == "done"
        assert not app.state.runs.busy(session.id)

    asyncio.run(exercise())


def test_terminal_foreground_event_never_blocks_cleanup_on_a_full_reader_queue():
    async def exercise():
        turns = SessionRuns()
        events = SessionEventStream()

        async def run(_turn):
            for _ in range(64):
                events.publish("session", {"type": "delta", "text": "output", "run_id": "turn"})
            events.publish("session", {"type": "done", "run_id": "turn"})

        turn = turns.start("session", run)
        await asyncio.wait_for(turn.wait(), timeout=1)
        assert not turns.busy("session")
        received = events.events_after("session")
        assert len(received) == 65
        assert received[-1].type == "done"
        assert received[-1].data == {"run_id": "turn"}
        await turns.close()

    asyncio.run(exercise())


def test_message_ack_and_get_replay_keep_execution_independent_of_readers():
    async def exercise():
        release = asyncio.Event()

        class Provider:
            async def stream_events(self, _messages, tools=None):
                yield TextDelta("Partial ")
                await release.wait()
                yield TextDelta("answer.")

        app = create_test_app(settings=make_settings(), provider=Provider())
        session = app.state.session_store.create("owner", schedule_yaml())
        observed = []
        unsubscribe = session.subscribe(lambda event: observed.append(event))

        async def read_until(event_type, cursor=0):
            received = asyncio.Queue()
            await received.put({"type": "http.request", "body": b"", "more_body": False})
            chunks = []

            async def send(message):
                if message["type"] == "http.response.body":
                    chunks.append(message.get("body", b""))
                    if f"event: {event_type}\n".encode() in b"".join(chunks):
                        await received.put({"type": "http.disconnect"})

            path = f"/sessions/{session.id}/events"
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [
                    (key.lower().encode(), value.encode())
                    for key, value in {
                        **AI_AUTH_HEADERS,
                        "Cookie": f"{OWNER_COOKIE}=owner",
                        "Last-Event-ID": str(cursor),
                    }.items()
                ],
                "client": ("127.0.0.1", 1),
                "server": ("testserver", 80),
            }
            await asyncio.wait_for(app(scope, received.get, send), 1)
            return b"".join(chunks).decode()

        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={**AI_AUTH_HEADERS, "Accept": "application/json", "Cookie": f"{OWNER_COOKIE}=owner"},
            ) as client,
        ):
            response = await client.post(f"/sessions/{session.id}/messages", json={"message": "Explain"})
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            assert session.active
            refused = await client.post(f"/sessions/{session.id}/messages", json={"message": "Again"})
            assert refused.status_code == 409
            first = await read_until("delta")
            cursor = max(int(line[4:]) for line in first.splitlines() if line.startswith("id: "))
            assert session.active
            release.set()
            while app.state.runs.busy(session.id):
                await asyncio.sleep(0)
            replay = await read_until("done", cursor)
            assert '"text": "answer."' in replay
            assert f'"run_id": "{run_id}"' in replay
            assert "Partial " not in replay
            assert "event: stopped" not in replay
            assert session.transcript[-1].text == "Partial answer."
            assert observed[0] == {"type": "run_start", "trigger": "user", "run_id": run_id}
            assert observed[-1] == {"type": "done", "run_id": run_id}
            unsubscribe()
            unsubscribe()
            count = len(observed)

            # A missed required event restores a compact snapshot, not a silently
            # truncated stream.
            app.state.session_event_stream._max_events = 1
            session.publish(
                {
                    "type": "tool",
                    "run_id": run_id,
                    "tool_call_id": "read-1",
                    "name": "read",
                    "arguments": "{}",
                    "result": "read",
                    "ok": True,
                }
            )
            recovery = await read_until("session_reset")
            data = json.loads(next(line[6:] for line in recovery.splitlines() if line.startswith("data: ")))
            assert data["active_run_id"] is None
            assert any(event["type"] == "done" for event in data["events"])
            assert len(observed) == count

    asyncio.run(exercise())


def test_retired_session_does_not_recreate_its_event_history():
    async def exercise():
        app = create_test_app(settings=make_settings(), provider=FakeProvider())
        session = app.state.session_store.create("owner", schedule_yaml())
        session.publish({"type": "done", "run_id": "old"})
        reader = session.events(1)
        waiting = asyncio.create_task(anext(reader, None))
        await asyncio.sleep(0)
        session.expires_at = 0
        app.state.session_store._prune_expired()
        assert app.state.session_store.get(session.id) is None
        assert await asyncio.wait_for(waiting, 1) is None
        session.publish(
            {
                "type": "optimization",
                "job_id": "late",
                "state": "completed",
                "terminal": True,
                "backend": {},
                "request": {},
                "result": None,
                "error": None,
                "downloadable": False,
            }
        )
        assert not app.state.session_event_stream.events_after(session.id)
        assert app.state.session_event_stream._retained_bytes == 0
        assert await anext(session.events(0), None) is None

    asyncio.run(exercise())


def test_optimizer_completion_can_retry_and_review_again_without_a_user_turn():
    from io import BytesIO
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from nurse_scheduling import schedule
    from nurse_scheduling.ai.attachment_tools.inspect_optimizer_result import inspect_result
    from nurse_scheduling.ai.optimizer import OptimizerArtifact
    from nurse_scheduling.ai.provider import ToolCall, ToolCallRequest
    from nurse_scheduling.ai.sandbox import CommandResult
    from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
    from nurse_scheduling.ai.workspace import WORKSPACE_RESULT_CONTEXT

    from .test_ai_basic import ScriptedToolProvider
    from .test_ai_optimizer import FakeOptimizerBackend

    async def exercise():
        class Backend(FakeOptimizerBackend):
            async def get(self, job_id):
                payload = await super().get(job_id)
                if payload.state == "completed":
                    payload.result = {
                        "outcome": "feasible",
                        "solver_status": "FEASIBLE",
                        "score": 0 if job_id == "remote-1" else 1,
                    }
                return payload

            async def result_artifact(self, job):
                source = self.submissions[int(job.id.rsplit("-", 1)[1]) - 1][0]
                first = job.id == "remote-1"
                forced = {
                    (day, shift, person): int(day == 0 and person == 0 and shift == (1 if first else 0))
                    for day in range(2)
                    for shift in range(2)
                    for person in range(2)
                }
                output = schedule(
                    source.encode(), solver="ortools/cp-sat", forced_solution=forced, timeout=5, prettify=True
                )
                from nurse_scheduling.exporter import export_to_excel

                output.dataframe.data.loc[output.dataframe.data.iloc[:, 0] == "Status"] = output.dataframe.data.loc[
                    output.dataframe.data.iloc[:, 0] == "Status"
                ].replace("OPTIMAL", "FEASIBLE")
                data = BytesIO()
                export_to_excel(output.dataframe, data, output.cell_export_info)
                return OptimizerArtifact(
                    data.getvalue(), "result.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        audits = []

        def inspect(_command, _timeout, sandbox):
            with TemporaryDirectory() as directory:
                workbook = Path(directory) / "result.xlsx"
                workbook.write_bytes(sandbox.files["/workspace/optimizer-results/optimized-schedule.xlsx"])
                context = json.loads(sandbox.files[WORKSPACE_RESULT_CONTEXT])
                result = inspect_result(workbook, context, context["source_sha256"])
            audits.append(result)
            return CommandResult(json.dumps(result), "", 0)

        start = [ToolCallRequest((ToolCall("start", "optimizer", '{"action":"start"}'),))]
        review = [ToolCallRequest((ToolCall("review", "bash", '{"command":"inspect result"}'),))]
        provider = ScriptedToolProvider(
            start,
            review,
            start,
            review,
            [TextDelta("Reviewed fresh result.")],
        )
        backend = Backend()
        backend.release.set()
        factory = FakeSandboxFactory(lambda id: FakeSandboxBackend(id, command_handler=inspect))
        app = create_test_app(
            settings=make_settings(optimizer_poll_interval_seconds=0.001),
            provider=provider,
            sandbox_factory=factory,
            optimizer_backend=backend,
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={**AI_AUTH_HEADERS, "Accept": "application/json"},
            ) as client,
        ):
            sid = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            response = await client.post(f"/sessions/{sid}/messages", json={"message": "Prepare and check the roster."})
            assert response.status_code == 202
            async with asyncio.timeout(5):
                while len(audits) < 2 or app.state.runs.busy(sid):
                    await asyncio.sleep(0.001)
            assert [a["summary"][0]["unmet"] for a in audits] == [1, 0]
            assert len(backend.submissions) == 2
            assert backend.deleted == ["remote-1", "remote-2"]
            events = app.state.session_event_stream.events_after(sid)
            assert [e.data["trigger"] for e in events if e.type == "run_start"] == ["user", "optimizer", "optimizer"]
            assert sum(e.type == "done" for e in events) == 3
            assert not any(e.type in {"stale", "error", "stopped"} for e in events)
            session = app.state.session_store.get(sid)
            assert session.transcript[-1] == AssistantMessage("Reviewed fresh result.")

    asyncio.run(exercise())


def test_analysis_commits_with_its_run_and_is_counted_in_retention():
    from nurse_scheduling.ai.workspace import AgentAnalysis

    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    before = store.retained_bytes
    snapshot = store.begin(session.id, "owner")
    snapshot.analysis = AgentAnalysis("a" * 64, b"confirmed source mapping")
    assert store.finish(session.id, [], snapshot=snapshot).run_saved
    assert session.analysis is snapshot.analysis
    assert store.retained_bytes == before + 64 + len(snapshot.analysis.content)
    next_run = store.begin(session.id, "owner")
    assert next_run.analysis is session.analysis
    store.abort(session.id, next_run)
    store.update_schedule(session.id, "owner", schedule_yaml() + "\n")
    assert session.analysis is None


def test_aborted_or_stale_runs_do_not_replace_retained_analysis():
    from nurse_scheduling.ai.workspace import AgentAnalysis

    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    original = store.begin(session.id, "owner")
    original.analysis = AgentAnalysis("a" * 64, b"original")
    store.finish(session.id, [], snapshot=original)
    aborted = store.begin(session.id, "owner")
    aborted.analysis = AgentAnalysis("b" * 64, b"discarded")
    store.abort(session.id, aborted)
    successor = store.begin(session.id, "owner")
    assert not store.finish(session.id, [], snapshot=aborted).run_saved
    assert session.analysis.content == b"original"
    store.update_schedule(session.id, "owner", schedule_yaml() + "\n")
    successor.analysis = AgentAnalysis("c" * 64, b"previous schedule")
    assert store.finish(session.id, [], snapshot=successor).run_saved
    # The schedule update queued during the run invalidates notes about the previous schedule.
    store.apply_queued_schedule(session.id)
    assert session.analysis is None


def test_optional_analysis_is_dropped_when_the_session_budget_is_full():
    from nurse_scheduling.ai.workspace import AgentAnalysis

    source = schedule_yaml()
    store = SessionStore(make_settings(max_session_bytes=len(source.encode()) + 10))
    session = store.create("owner", source)
    snapshot = store.begin(session.id, "owner")
    snapshot.analysis = AgentAnalysis("a" * 64, b"notes exceed available budget")
    assert store.finish(session.id, [], snapshot=snapshot).run_saved
    assert session.analysis is None
    assert store.retained_bytes == len(source.encode())


def test_optional_analysis_does_not_block_new_session_input():
    from nurse_scheduling.ai.workspace import AgentAnalysis

    source = schedule_yaml()
    store = SessionStore(make_settings(max_session_bytes=len(source.encode()) + 150))
    session = store.create("owner", source)
    snapshot = store.begin(session.id, "owner")
    snapshot.analysis = AgentAnalysis("a" * 64, b"cached analysis")
    store.finish(session.id, [], snapshot=snapshot)
    assert session.analysis is not None
    store.create("another-owner", "x" * 100)
    assert session.analysis is None
    assert store.retained_bytes == len(source.encode()) + 100
