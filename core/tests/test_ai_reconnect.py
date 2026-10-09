"""Reconnect and message delivery regressions for the AI service."""

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
from uuid import uuid4

import httpx

from nurse_scheduling.ai.app import OWNER_COOKIE
from nurse_scheduling.ai.history import ChatHistory
from nurse_scheduling.ai.provider import TextDelta
from nurse_scheduling.ai.session_event_stream import SessionEventBroker

from . import test_ai_basic as basic


def test_repeated_submission_after_lost_completion_does_not_repeat_the_question():
    provider = basic.FakeProvider([["Saved answer"], ["Duplicate answer"]])
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        request = {"message": "Original question", "message_id": str(uuid4())}
        first = client.post(f"/sessions/{session}/messages", json=request)
        repeated = client.post(f"/sessions/{session}/messages", json=request)
        assert first.status_code == repeated.status_code == 200
        assert len(provider.calls) == 1
        history = app.state.session_store._sessions[session].history
        assert sum(message["content"] == "Original question" for message in history) == 1
        assert "Saved answer" in repeated.text


def test_agent_completes_after_browser_disconnects_mid_response():
    async def exercise():
        release = asyncio.Event()
        completed = asyncio.Event()
        disconnected = asyncio.Event()

        class Provider:
            async def stream_events(self, messages, tools=None):
                yield TextDelta("First part")
                await release.wait()
                yield TextDelta(" and completed answer")
                completed.set()

        app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
        session = app.state.session_store.create("browser-owner", basic.schedule_yaml())
        requests = asyncio.Queue()
        await requests.put(
            {"type": "http.request", "body": json.dumps({"message": "Keep working"}).encode(), "more_body": False}
        )

        async def receive():
            return await requests.get()

        async def send(message):
            if (
                message["type"] == "http.response.body"
                and b"First part" in message.get("body", b"")
                and not disconnected.is_set()
            ):
                disconnected.set()
                await requests.put({"type": "http.disconnect"})
                await asyncio.sleep(0)

        path = f"/sessions/{session.id}/messages"
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"authorization", f"Bearer {basic.AI_AUTH_TOKEN}".encode()),
                (b"content-type", b"application/json"),
                (b"cookie", f"{OWNER_COOKIE}=browser-owner".encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        await asyncio.wait_for(app(scope, receive, send), timeout=2)
        assert disconnected.is_set()
        release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        await asyncio.wait_for(
            asyncio.gather(*(turn.done for pending in app.state.turns._turns.values() for turn in pending)), timeout=1
        )
        assert not session.active
        assert session.history[-1]["content"] == "First part and completed answer"

    asyncio.run(exercise())


def test_reconnect_recovers_all_background_text_after_buffer_overflow():
    async def exercise():
        broker = SessionEventBroker(max_events_per_session=2)
        broker.publish("session", "turn_start", {"message_id": "answer", "trigger": "optimizer"})
        for text in ("First ", "middle ", "last"):
            broker.publish("session", "delta", {"text": text})
        broker.publish("session", "done", {"message_id": "answer"})
        stream = broker.stream("session", 0)
        event = await anext(stream)
        await stream.aclose()
        assert event.type == "session_snapshot"
        text = "".join(item["data"]["text"] for item in event.data["events"] if item["type"] == "delta")
        assert text == "First middle last"

    asyncio.run(exercise())


def test_stop_after_answer_saved_reports_completion(monkeypatch):
    async def exercise():
        saving = asyncio.Event()
        release = asyncio.Event()
        original_write = ChatHistory.write

        async def write(self, operation, *args):
            if operation == "finish_recovery_turn":
                saving.set()
                await release.wait()
            return await original_write(self, operation, *args)

        monkeypatch.setattr(ChatHistory, "write", write)
        monkeypatch.setattr(ChatHistory, "initialize", lambda *_args: None)
        monkeypatch.setattr(ChatHistory, "start_recovery_turn", lambda *_args: None)
        for operation in (
            "save_recovery_session",
            "start_recovery_turn",
            "append_recovery_event",
            "finish_recovery_turn",
            "load_recovery_turn",
            "stop_recovery_request",
            "recovery_request_stopped",
        ):
            monkeypatch.setattr(ChatHistory, operation, lambda *_args: None)
        provider = basic.FakeProvider([["Completed answer"]])
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            response = asyncio.create_task(
                client.post(
                    f"/sessions/{session}/messages",
                    json={
                        "message": "Original question",
                        "message_id": "stop-completion-race",
                    },
                )
            )
            await asyncio.wait_for(saving.wait(), timeout=1)
            assert (await client.post(f"/sessions/{session}/stop")).status_code == 202
            release.set()
            result = await asyncio.wait_for(response, timeout=2)
            assert basic.parse_sse(result.text)[-1][0] == "done"
            history = app.state.session_store._sessions[session].history
            assert [message["content"] for message in history] == ["Original question", "Completed answer"]
            assert len(provider.calls) == 1

    asyncio.run(exercise())


def test_foreground_replay_recovers_prefix_after_more_than_one_thousand_fragments():
    from nurse_scheduling.ai.turns import ReplayTurn

    async def exercise():
        turn = ReplayTurn("turn", "session", "request", "Original question")
        for index, text in enumerate(["First", *[" middle" for _ in range(1200)], " last"], start=1):
            turn.append(index, "delta", {"text": text})
        turn.append(turn.cursor + 1, "done", {"message_id": "turn"})
        stream = turn.stream(0)
        event_id, event_type, data = await anext(stream)
        assert event_type == "turn_snapshot"
        assert event_id == turn.cursor
        assert data["events"][0]["data"]["text"] == "First" + " middle" * 1200 + " last"
        assert data["events"][-1]["type"] == "done"
        await stream.aclose()

    asyncio.run(exercise())


def test_stop_before_message_arrives_prevents_provider_execution():
    provider = basic.FakeProvider([["This must not be sent"]])
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        request = {"message": "Original question", "message_id": "stopped-request"}
        assert client.post(f"/sessions/{session}/stop", json={"message_id": request["message_id"]}).status_code == 202
        result = client.post(f"/sessions/{session}/messages", json=request)
        assert basic.parse_sse(result.text, include_model_input=True)[-1][0] == "stopped"
        assert provider.calls == []
        assert app.state.session_store._sessions[session].history == [
            {"role": "user", "content": "Original question"},
            {"role": "assistant", "content": basic.ABORTED_RESPONSE_HISTORY},
        ]


def test_stop_for_an_earlier_message_leaves_the_active_turn_running():
    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider:
            async def stream_events(self, _messages, tools=None):
                started.set()
                await release.wait()
                yield TextDelta("Current answer")

        app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            turn = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Current", "message_id": "current"})
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            stop = await client.post(f"/sessions/{session_id}/stop", json={"message_id": "earlier"})
            assert stop.status_code == 202
            release.set()
            response = await asyncio.wait_for(turn, timeout=2)
            return basic.parse_sse(response.text)[-1][0]

    assert asyncio.run(exercise()) == "done"


def test_replay_cache_without_recovery_keeps_each_sessions_newest_turn():
    from nurse_scheduling.ai.turns import TurnJournal

    async def exercise():
        journal = TurnJournal(None, max_cached_bytes=1)
        for session, request in (("a", "old"), ("b", "only"), ("a", "new")):
            turn = await journal.start(session, request, request, "Question")
            await journal.publish(turn, "delta", {"text": "Answer"})
            await journal.finish(turn, "done", {"message_id": request}, state=())
        running = await journal.start("a", "running", "running", "Question")
        await journal.publish(running, "delta", {"text": "Partial"})
        journal.trim_cache()
        return set(journal.turns)

    assert asyncio.run(exercise()) == {("a", "running"), ("b", "only")}


def test_background_snapshot_without_recovery_keeps_newest_output_within_budget():
    broker = SessionEventBroker(max_events_per_session=2, max_snapshot_bytes=200)
    for index in range(20):
        broker.publish("session", "warning", {"message": f"Entry {index:02d}"})
    snapshot = broker._snapshots["session"]
    retained = sum(len(json.dumps(entry["data"]).encode()) for entry in snapshot)
    assert retained <= 200
    assert broker._snapshot_bytes["session"] == retained
    assert snapshot[-1]["data"]["message"] == "Entry 19"
