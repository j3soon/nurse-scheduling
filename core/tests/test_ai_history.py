"""AI chat history, session recovery, and PostgreSQL persistence checks."""

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
import hashlib
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql

from nurse_scheduling.ai import history as history_module
from nurse_scheduling.ai.agent_session import BACKGROUND_RECOVERY_ERROR, RECOVERY_SAVE_WARNING
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.history import ChatHistory, _insert_entries
from nurse_scheduling.ai.provider import ProviderError, ReasoningDelta, TextDelta, TokenUsage
from nurse_scheduling.ai.recovery import _event_rows
from nurse_scheduling.ai.session_event_stream import SessionEvent, fold_recovery
from nurse_scheduling.ai.transcript import (
    AppEventEntry,
    AssistantMessage,
    ProposalDecisionEntry,
    ToolCall,
    ToolResultImage,
    ToolResultMessage,
    UserMessage,
)

from . import test_ai_basic as basic

EMPTY_STATE = {
    "schedule_yaml": basic.schedule_yaml(),
    "pending_proposal": None,
    "dropped_history_messages": 0,
    "dropped_entries": 0,
}


def unavailable(*_args, **_kwargs):
    raise psycopg.OperationalError("secret-database-url")


def test_history_environment_settings(monkeypatch):
    for name, value in {
        "AI_PROVIDER_API_KEY": "test-token",
        "AI_PROVIDER_BASE_URL": "https://provider.example/v1",
        "AI_SANDBOX_BACKEND": "e2b",
        "E2B_API_KEY": "test-e2b-key",
        "AI_HISTORY_POSTGRES_URL": " postgresql:///history ",
        "AI_SESSION_TTL_SECONDS": "604800",
    }.items():
        monkeypatch.setenv(name, value)
    settings = AiSettings.from_env()
    assert settings.history_postgres_url == "postgresql:///history"
    assert settings.session_ttl_seconds == 604800
    monkeypatch.setenv("AI_SESSION_TTL_SECONDS", "0")
    with pytest.raises(ValueError, match="AI_SESSION_TTL_SECONDS"):
        AiSettings.from_env()


def test_recovery_default_session_lifetime():
    assert basic.make_settings().session_ttl_seconds == 30 * 24 * 60 * 60


@pytest.fixture
def recorded_history(monkeypatch):
    records = {"starts": [], "finishes": [], "saves": [], "entries": []}

    def start(_self, run_id, session_id, *, state, prompt, prompt_seq, entries=(), **fields):
        records["entries"].extend([*entries, (prompt_seq, run_id, UserMessage(prompt))])
        records["starts"].append(
            {"run_id": run_id, "session_id": session_id, "state": state, "prompt": prompt, **fields}
        )

    def finish(_self, *outcome, session_id=None, state=None, entries=()):
        records["entries"].extend(entries)
        records["finishes"].append((*outcome, state))

    def save(_self, *_args, entries=(), **kwargs):
        records["entries"].extend(entries)
        records["saves"].append(kwargs)

    monkeypatch.setattr(ChatHistory, "initialize", lambda _self: None)
    monkeypatch.setattr(ChatHistory, "start_run", start)
    monkeypatch.setattr(ChatHistory, "finish_run", finish)
    monkeypatch.setattr(ChatHistory, "save_session", save)
    monkeypatch.setattr(
        ChatHistory, "append_entries", lambda _self, _session_id, entries: records["entries"].extend(entries)
    )
    for operation in ("append_events", "stop_message", "message_stopped", "find_message", "load_session"):
        monkeypatch.setattr(ChatHistory, operation, lambda *_args, **_kwargs: None)
    return records


def run_messages(records, run_id: str) -> list:
    """Return the saved messages of one run in session order, starting with its prompt."""
    return [
        entry for _seq, saved_run, entry in sorted(records["entries"], key=lambda row: row[0]) if saved_run == run_id
    ]


@pytest.mark.parametrize("failed", [False, True])
def test_records_text_usage_and_sanitized_failure(recorded_history, failed):
    class Provider:
        async def stream_events(self, messages, tools=None):
            yield TextDelta("Partial answer")
            yield TokenUsage(2, 3, 5)
            yield TokenUsage(1, 1, 2)
            if failed:
                raise ProviderError("private provider credential")

    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=Provider())
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
    (start,) = recorded_history["starts"]
    (finish,) = recorded_history["finishes"]
    assert (start["session_id"], start["prompt"], start["model"]) == (session_id, "Question", "test-model")
    assert (start["attachment_count"], start["kind"], start["message_id"]) == (0, "foreground", None)
    # Both completed and interrupted runs retain safe conversation context.
    assert finish[:5] == (
        start["run_id"],
        "failed" if failed else "completed",
        "provider_error" if failed else None,
        TokenUsage(3, 4, 7),
        True,
    )
    assert run_messages(recorded_history, start["run_id"]) == [
        UserMessage("Question"),
        AssistantMessage("Partial answer", "error" if failed else "stop"),
    ]
    if not failed:
        assert basic.parse_sse(response.text)[-1] == ("done", {"run_id": start["run_id"], "history_saved": True})
    assert "private provider credential" not in repr(recorded_history)


def test_database_unavailable_releases_session_before_provider_call(recorded_history, monkeypatch):
    monkeypatch.setattr(ChatHistory, "start_run", unavailable)
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
        assert response.status_code == 503
        assert provider.calls == []
        session = app.state.session_store._sessions[session_id]
        assert session.transcript == []
        assert session.dropped_entries == 0
        monkeypatch.setattr(ChatHistory, "start_run", lambda *_args, **_kwargs: None)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
        assert basic.parse_sse(response.text)[-1][0] == "done"
        assert session.transcript.count(UserMessage("Question")) == 1


def test_final_write_failure_preserves_successful_conversation(recorded_history, monkeypatch, caplog):
    monkeypatch.setattr(ChatHistory, "finish_run", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
    events = basic.parse_sse(response.text)
    assert ("warning", {"message": RECOVERY_SAVE_WARNING, "run_id": events[-1][1]["run_id"]}) in events
    assert events[-1][1]["history_saved"] is False
    assert "AI history finish_run failed" in caplog.text
    assert "secret-database-url" not in caplog.text


def test_records_queued_steering_in_run_order(recorded_history):
    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def stream_events(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                yield TextDelta("Monday is covered.")
                store = app.state.session_store
                (session_id,) = store._sessions
                store.queue_steering(session_id, store._sessions[session_id].owner_token, "queued-1", "And Tuesday?")
            else:
                yield TextDelta("Tuesday is covered.")

    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=Provider())
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        client.post(f"/sessions/{session_id}/messages", json={"message": "Is Monday covered?"})

    (start,) = recorded_history["starts"]
    assert run_messages(recorded_history, start["run_id"]) == [
        UserMessage("Is Monday covered?"),
        AssistantMessage("Monday is covered."),
        UserMessage("And Tuesday?"),
        AssistantMessage("Tuesday is covered."),
    ]


def test_history_records_the_typed_prompt_and_the_retained_upload_count(recorded_history):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"),
        provider=basic.FakeProvider([["Seen."]]),
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        basic.upload_files(client, session_id, ("ward.xlsx", b"bytes", "application/octet-stream"))
        client.post(f"/sessions/{session_id}/messages", json={"message": "Read this."})
        transcript = app.state.session_store._sessions[session_id].transcript

    (start,) = recorded_history["starts"]
    # The upload is its own session history entry, so the run prompt stays as typed.
    assert (start["prompt"], start["model"], start["attachment_count"]) == ("Read this.", "test-model", 1)
    assert transcript[1] == UserMessage("Read this.")
    assert "ward.xlsx" in transcript[0].text


def test_history_keeps_the_full_run_while_the_session_keeps_only_later_context(recorded_history):
    provider = basic.ScriptedToolProvider(
        [ReasoningDelta("Find P1. "), basic.TextDelta("Checking. "), *basic.rename_call()],
        [basic.TextDelta("Renamed P1.")],
    )
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test", max_schedule_bytes=basic.SCHEDULE_BYTE_LIMIT),
        provider=provider,
        sandbox_factory=basic.rename_factory(),
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client, basic.schedule_yaml())
        client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})
        retained = app.state.session_store._sessions[session_id].transcript

    (start,) = recorded_history["starts"]
    (call,) = basic.rename_call()[0].calls
    prompt, tool_use, tool_result, answer = run_messages(recorded_history, start["run_id"])
    assert prompt == UserMessage("Rename P1.")
    assert tool_use == AssistantMessage("Checking. ", "tool_use", "Find P1. ", (call,))
    assert (tool_result.tool_call_id, tool_result.tool_name, tool_result.ok) == (call.id, call.name, True)
    assert "passed trusted server-side validation" in tool_result.text
    assert answer == AssistantMessage("Renamed P1.")
    assert retained == [UserMessage("Rename P1."), AssistantMessage("Checking. ", "tool_use"), answer]


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_proposal_decisions_join_the_run_that_proposed_them(recorded_history, decision):
    client, session_id, revision = basic.proposing_client(history_postgres_url="test")
    with client:
        if decision == "approved":
            response = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
        else:
            response = client.post(f"/sessions/{session_id}/proposal/reject")
        assert response.json()["history_saved"] is True
        # Without a pending proposal no decision is recorded, but the state is saved.
        saves = len(recorded_history["saves"])
        assert client.post(f"/sessions/{session_id}/proposal/reject").json()["history_saved"] is True
        assert len(recorded_history["saves"]) == saves + 1

    (start,) = recorded_history["starts"]
    decisions = [
        (run_id, entry)
        for _seq, run_id, entry in recorded_history["entries"]
        if isinstance(entry, ProposalDecisionEntry)
    ]
    assert decisions == [(start["run_id"], ProposalDecisionEntry(decision))]


def test_database_unavailable_prevents_startup(recorded_history, monkeypatch):
    monkeypatch.setattr(ChatHistory, "initialize", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with pytest.raises(RuntimeError, match="database initialization failed"), basic.AuthenticatedTestClient(app):
        pass


def test_failed_session_save_releases_the_session_slot(recorded_history, monkeypatch):
    monkeypatch.setattr(ChatHistory, "save_session", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        response = client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})
    assert response.status_code == 503
    assert app.state.session_store._sessions == {}
    assert app.state.session_store.retained_bytes == 0


def test_recovery_read_failure_during_message_lookup_returns_503(recorded_history, monkeypatch):
    monkeypatch.setattr(ChatHistory, "find_message", unavailable)
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question", "message_id": "m1"})
    assert response.status_code == 503
    assert provider.calls == []


@asynccontextmanager
async def serving(app, owner: str | None = None):
    """Run the application lifespan with an HTTP client that receives JSON acknowledgements."""
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}", "Accept": "application/json"},
            cookies={basic.OWNER_COOKIE: owner} if owner else None,
        ) as client,
    ):
        yield client


async def read_events(
    app, session_id: str, owner: str, cursor: int = 0, until: str = "done", *, reset: bool = False
) -> list[tuple]:
    """Read the session stream from a cursor until an event type arrives, and return its frames."""
    requests = asyncio.Queue()
    await requests.put({"type": "http.request", "body": b"", "more_body": False})
    chunks = []

    async def send(message):
        if message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))
            if f"event: {until}\n".encode() in b"".join(chunks):
                await requests.put({"type": "http.disconnect"})

    path = f"/sessions/{session_id}/events"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"reset=true" if reset else b"",
        "root_path": "",
        "headers": [
            (b"authorization", f"Bearer {basic.AI_AUTH_TOKEN}".encode()),
            (b"cookie", f"{basic.OWNER_COOKIE}={owner}".encode()),
            (b"last-event-id", str(cursor).encode()),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    await asyncio.wait_for(app(scope, requests.get, send), 5)
    frames = []
    for block in b"".join(chunks).decode().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in fields:
            frames.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return frames


def reset_text(frames: list[tuple]) -> str:
    """Return the answer text that a recovery reset replays."""
    (reset,) = [data for _id, kind, data in frames if kind == "session_reset"]
    return "".join(item["data"].get("text", "") for item in reset["events"] if item["type"] == "delta")


def test_stop_during_failed_run_start_does_not_stop_next_run(recorded_history, monkeypatch):
    release = threading.Event()
    entered = threading.Event()

    def start(*_args, **_kwargs):
        entered.set()
        release.wait(5)
        raise psycopg.OperationalError("secret-database-url")

    provider = basic.FakeProvider()

    async def exercise():
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            monkeypatch.setattr(ChatHistory, "start_run", start)
            first = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "First"}))
            await asyncio.to_thread(entered.wait, 5)
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            release.set()
            assert (await first).status_code == 202
            monkeypatch.setattr(ChatHistory, "start_run", lambda *_args, **_kwargs: None)
            second = await client.post(f"/sessions/{session_id}/messages", json={"message": "Second"})
            owner = client.cookies[basic.OWNER_COOKIE]
            frames = await read_events(app, session_id, owner)
            return second.json()["run_id"], frames

    run_id, frames = asyncio.run(exercise())
    assert [kind for _id, kind, data in frames if kind in {"stopped", "done"}] == ["stopped", "done"]
    assert frames[-1][2]["run_id"] == run_id
    assert len(provider.calls) == 1
    # The stopped run has no saved record, so no messages or outcome follow it.
    assert [finish[0] for finish in recorded_history["finishes"]] == [run_id]
    assert {saved_run for _seq, saved_run, _entry in recorded_history["entries"]} == {run_id}


def test_disconnected_admission_still_runs_and_releases_the_session(recorded_history, monkeypatch):
    blocked = threading.Event()
    release = threading.Event()

    def start(*_args, **_kwargs):
        blocked.set()
        release.wait(5)

    provider = basic.FakeProvider([["First answer"], ["Second answer"]])

    async def exercise():
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            monkeypatch.setattr(ChatHistory, "start_run", start)
            first = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "First"}))
            await asyncio.to_thread(blocked.wait, 5)
            # A lost request does not cancel accepted work.
            first.cancel()
            release.set()
            await asyncio.gather(first, return_exceptions=True)
            while app.state.runs.busy(session_id):
                await asyncio.sleep(0.01)
            assert not app.state.session_store._sessions[session_id].active
            second = await client.post(f"/sessions/{session_id}/messages", json={"message": "Second"})
            assert second.status_code == 202
            while app.state.runs.busy(session_id):
                await asyncio.sleep(0.01)

    asyncio.run(exercise())
    assert len(provider.calls) == 2


def test_recovery_state_writes_commit_in_capture_order(recorded_history, monkeypatch):
    older, newer = "description: older", "description: newer"
    blocked = threading.Event()
    release = threading.Event()
    committed = []

    def save(_self, _session_id, *, state, credential_id=None, entries=()):
        if state[2]["schedule_yaml"] == older:
            blocked.set()
            release.wait(5)
        committed.append(state[2]["schedule_yaml"])

    monkeypatch.setattr(ChatHistory, "save_session", save)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
        )
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            path = f"/sessions/{session_id}/schedule"
            first = asyncio.create_task(client.put(path, json={"schedule_yaml": older}))
            await asyncio.to_thread(blocked.wait, 5)
            second = asyncio.create_task(client.put(path, json={"schedule_yaml": newer}))
            # Without serialization, the newer state commits while the older write is blocked.
            await asyncio.sleep(0.1)
            assert newer not in committed
            release.set()
            assert [(await first).status_code, (await second).status_code] == [204, 204]

    asyncio.run(exercise())
    assert committed[-2:] == [older, newer]


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_proposal_decision_reports_a_failed_recovery_save(recorded_history, monkeypatch, decision):
    client, session_id, revision = basic.proposing_client(history_postgres_url="test")
    monkeypatch.setattr(ChatHistory, "save_session", unavailable)
    body = {"base_sha256": revision} if decision == "approve" else None
    with client:
        response = client.post(f"/sessions/{session_id}/proposal/{decision}", json=body)
    assert response.status_code == 200
    assert response.json()["history_saved"] is False
    assert client.app.state.session_store._sessions[session_id].pending_proposal is None


def test_schedule_update_that_cannot_be_saved_can_be_retried(recorded_history, monkeypatch):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        path = f"/sessions/{session_id}/schedule"
        monkeypatch.setattr(ChatHistory, "save_session", unavailable)
        assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 503
        monkeypatch.setattr(ChatHistory, "save_session", lambda *_args, **_kwargs: None)
        assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 204


def test_full_store_evicts_the_least_recently_used_idle_session(recorded_history):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test", max_sessions=2), provider=basic.FakeProvider()
    )
    store = app.state.session_store
    with basic.AuthenticatedTestClient(app) as client:
        first = basic.create_session(client)
        second = basic.create_session(client)
        for session_id in (first, second):
            store._sessions[session_id].snapshot = object()
        assert client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()}).status_code == 429
        for session_id in (first, second):
            store._sessions[session_id].snapshot = None
        assert client.get(f"/sessions/{first}/uploads").status_code == 200
        third = basic.create_session(client)
    assert list(store._sessions) == [first, third]


@pytest.mark.parametrize("operation", ["finish_run", "save_session"])
def test_full_store_keeps_a_session_until_its_state_write_ends(recorded_history, monkeypatch, operation):
    blocked = threading.Event()
    release = threading.Event()

    def write(*_args, **_kwargs):
        blocked.set()
        release.wait(5)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test", max_sessions=1), provider=basic.FakeProvider()
        )
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            monkeypatch.setattr(ChatHistory, operation, write)
            if operation == "finish_run":
                request = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
            else:
                request = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": "description: newer"})
            pending = asyncio.create_task(request)
            await asyncio.to_thread(blocked.wait, 5)
            # The session is idle while its write runs, but eviction would make the write fail.
            assert app.state.session_store._sessions[session_id].active is False
            assert (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).status_code == 429
            release.set()
            assert (await pending).status_code in {202, 204}
            while app.state.runs.busy(session_id):
                await asyncio.sleep(0.01)
            await app.state.recovery.flush(session_id)
            assert (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).status_code == 201

    asyncio.run(exercise())


@pytest.mark.parametrize("operation", ["finish_run", "save_session"])
def test_full_store_keeps_a_session_whose_state_was_not_saved(recorded_history, monkeypatch, operation):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test", max_sessions=1), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        path = f"/sessions/{session_id}/schedule"
        with monkeypatch.context() as patch:
            patch.setattr(ChatHistory, operation, unavailable)
            if operation == "finish_run":
                response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
                assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
            else:
                assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 503
        # Memory holds the only copy of the newest state until a save succeeds.
        assert client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()}).status_code == 429
        assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 204
        basic.create_session(client)
    assert session_id not in app.state.session_store._sessions
    if operation == "finish_run":
        # The schedule save also retried the answer's final outcome with the newer state.
        [retried] = recorded_history["finishes"]
        assert retried[1] == "completed"
        assert retried[5][2]["schedule_yaml"] == "description: newer"


def test_full_store_without_recovery_keeps_refusing_new_sessions():
    app = basic.create_test_app(settings=basic.make_settings(max_sessions=1), provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(app) as client:
        basic.create_session(client)
        response = client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})
    assert response.status_code == 429


@pytest.mark.parametrize("failing", [("append_events",), ("start_run", "finish_run")])
def test_background_recovery_outage_releases_session_and_reports_status(recorded_history, monkeypatch, failing):
    for operation in (*failing, "save_session"):
        monkeypatch.setattr(ChatHistory, operation, unavailable)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
        )
        session = app.state.session_store.create(str(uuid4()), basic.schedule_yaml())
        optimizer = app.state.session_optimizer
        await optimizer._on_update(session.id, {"job_id": "job", "state": "completed", "terminal": True})
        await optimizer._on_completion(session.id, "Review the optimizer result.", None)
        events = app.state.session_event_stream.events_after(session.id)
        return events, session

    events, session = asyncio.run(exercise())
    assert events[0].type == "optimization"
    # Terminal and optimizer status events are delivered even when they cannot be saved.
    assert events[-1].type in {"done", "error"}
    if "start_run" in failing:
        assert events[-1].data["message"] == BACKGROUND_RECOVERY_ERROR
        assert session.transcript == []
        assert session.dropped_entries == 0
    assert not session.active


def record(entry) -> tuple[str, dict]:
    """Return the stored type and payload expected for one agent message."""
    kind = {
        UserMessage: "user",
        AssistantMessage: "assistant",
        ToolResultMessage: "tool_result",
        ProposalDecisionEntry: "proposal_decision",
        AppEventEntry: "app_event",
    }[type(entry)]
    # JSON stores tuples as arrays.
    payload = asdict(entry)
    if isinstance(entry, ToolResultMessage):
        payload.pop("image")
    return kind, json.loads(json.dumps(payload))


def test_history_excludes_in_run_tool_images():
    class Cursor:
        def __init__(self):
            self.rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def executemany(self, _query, rows):
            self.rows.extend(rows)

    class Connection:
        def __init__(self):
            self.saved = Cursor()

        def cursor(self):
            return self.saved

    connection = Connection()
    result = ToolResultMessage("call-1", "read", "Image inspected.", True, ToolResultImage("image/png", b"raw"))
    _insert_entries(connection, "session-1", [(1, "run-1", result)])

    assert connection.saved.rows[0][4].obj == {
        "tool_call_id": "call-1",
        "tool_name": "read",
        "text": "Image inspected.",
        "ok": True,
    }


def session_entries(connection) -> list[tuple[str, dict]]:
    """Return every saved entry in session order."""
    return connection.execute("SELECT type, payload FROM chat_session_entries ORDER BY session_id, seq").fetchall()


@pytest.fixture
def uninitialized_postgres_history(monkeypatch):
    database_url = os.getenv("AI_HISTORY_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set AI_HISTORY_TEST_POSTGRES_URL to run PostgreSQL integration checks")
    schema = "ai_history_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect(_self):
        return psycopg.connect(database_url, options=f"-c search_path={schema} -c statement_timeout=5000")

    monkeypatch.setattr(ChatHistory, "_connect", connect)
    try:
        yield ChatHistory(database_url)
    finally:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def postgres_history(uninitialized_postgres_history):
    uninitialized_postgres_history.initialize()
    return uninitialized_postgres_history


def session_state(owner: str, expires_in: float = 60, **changes) -> tuple[str, float, dict]:
    return owner, time.time() + expires_in, {**EMPTY_STATE, **changes}


def test_postgres_duplicates_and_reconnection(postgres_history):
    history = postgres_history
    run, session, owner = str(uuid4()), str(uuid4()), str(uuid4())
    history.save_session(session, session_state(owner), "team-a")
    history.start_run(run, session, session_state(owner), "What's next?", 0, model="model", attachment_count=3)
    history.start_run(run, session, session_state(owner), "duplicate", 1, model="model", attachment_count=3)
    call = ToolCall("call-1", "read", '{"path":"schedule.yaml"}')
    entries = [
        AssistantMessage("Checking.", "tool_use", "Look first.", (call,)),
        ToolResultMessage("call-1", "read", "people: []", True),
        UserMessage("Only nights."),
        AssistantMessage("Answer"),
    ]
    history.append_entries(session, [(seq, run, entry) for seq, entry in enumerate(entries, 1)])
    # A retried batch keeps the first copy.
    history.append_entries(session, [(1, run, AssistantMessage("Overwrite"))])
    state = session_state(owner)
    history.finish_run(run, "completed", None, TokenUsage(1, 2, 3), True, session_id=session, state=state)
    history.finish_run(run, "cancelled", None, None, False, session_id=session, state=state)
    decision = (5, run, ProposalDecisionEntry("approved"))
    history.save_session(session, state, entries=[decision])
    restarted = ChatHistory("test")
    restarted.initialize()
    with restarted._connect() as connection:
        row = connection.execute(
            "SELECT status, usage, finished_at, attachment_count, auth_credential_id, kind, committed FROM chat_runs"
        ).fetchone()
        assert row[:2] == (
            "completed",
            {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "cached_prompt_tokens": None,
                "reasoning_tokens": 0,
            },
        )
        assert row[2] is not None
        # A run without its own credential ID takes the session's. The first outcome stays.
        assert row[3:] == (3, "team-a", "foreground", True)
        assert session_entries(connection) == [
            record(UserMessage("What's next?")),
            *map(record, entries),
            record(ProposalDecisionEntry("approved")),
        ]
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (4,)
    # Tool results never join later context, so the conversation is rebuilt without them.
    assert restarted.load_session(session, owner)["entries"] == [
        UserMessage("What's next?"),
        entries[0],
        UserMessage("Only nights."),
        AssistantMessage("Answer"),
        ProposalDecisionEntry("approved"),
    ]


def test_postgres_stores_tool_output_with_nul_characters(postgres_history):
    run, session, owner = str(uuid4()), str(uuid4()), str(uuid4())
    postgres_history.save_session(session, session_state(owner))
    postgres_history.start_run(run, session, session_state(owner), "Inspect", 0, model="model", attachment_count=0)
    postgres_history.append_entries(session, [(1, run, ToolResultMessage("call-1", "bash", "a\x00b", True))])
    postgres_history.append_events(session, [(1, 1, run, "tool", {"result": "a\x00b", "run_id": run})])
    with postgres_history._connect() as connection:
        assert session_entries(connection)[-1][1]["text"] == "a\ufffdb"
    assert postgres_history.load_events(session, 0)[0][4]["result"] == "a\ufffdb"


def test_postgres_writes_survive_cancel_scope(postgres_history):
    import anyio

    run, session, owner = str(uuid4()), str(uuid4()), str(uuid4())
    postgres_history.save_session(session, session_state(owner))
    postgres_history.start_run(run, session, session_state(owner), "question", 0, model="model", attachment_count=0)

    async def cancel_and_save():
        with anyio.CancelScope() as scope:
            scope.cancel()
            assert await postgres_history.write(
                "finish_run",
                run,
                "cancelled",
                None,
                None,
                True,
                session_id=session,
                state=session_state(owner),
                entries=[(1, run, AssistantMessage("partial", "aborted"))],
            )

    asyncio.run(cancel_and_save())
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_runs").fetchone() == ("cancelled",)
        assert session_entries(connection)[-1] == record(AssistantMessage("partial", "aborted"))


def test_postgres_finish_commits_status_state_and_entries_together(postgres_history):
    history = postgres_history
    run, session, owner = str(uuid4()), str(uuid4()), str(uuid4())
    history.save_session(session, session_state(owner))
    history.start_run(run, session, session_state(owner), "Question", 0, model="model", attachment_count=0)
    answered = session_state(owner, schedule_yaml="description: answered")
    with pytest.raises(TypeError):
        history.finish_run(
            run, "completed", None, None, True, session_id=session, state=answered, entries=[(1, run, object())]
        )
    assert history.load_session(session, owner)["state"] == EMPTY_STATE
    with history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_runs").fetchone() == ("running",)
    entries = [(1, run, AssistantMessage("Answer"))]
    history.finish_run(run, "completed", None, None, True, session_id=session, state=answered, entries=entries)
    restored = history.load_session(session, owner)
    assert restored["state"] == answered[2]
    assert (restored["entries"], restored["next_entry_seq"]) == (
        [UserMessage("Question"), AssistantMessage("Answer")],
        2,
    )
    with history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_runs").fetchone() == ("completed",)


def test_postgres_event_rows_combine_fragments_without_losing_boundaries(postgres_history):
    session, owner, run = str(uuid4()), str(uuid4()), str(uuid4())
    postgres_history.save_session(session, session_state(owner))
    events = [
        SessionEvent(1, "run_start", {"trigger": "user", "run_id": run}),
        SessionEvent(2, "reasoning", {"text": "Think ", "run_id": run}),
        SessionEvent(3, "reasoning", {"text": "carefully", "run_id": run}),
        SessionEvent(4, "tool_start", {"name": "read", "run_id": run}),
        *(SessionEvent(cursor, "delta", {"text": "x", "run_id": run}) for cursor in range(5, 45)),
        SessionEvent(45, "optimization", {"job_id": "job", "state": "running"}),
        SessionEvent(46, "context_usage", {"used_chars": 10, "max_chars": 100, "run_id": run}),
        SessionEvent(47, "context_usage", {"used_chars": 20, "max_chars": 100, "run_id": run}),
        SessionEvent(48, "delta", {"text": "After status", "run_id": run}),
    ]
    rows = _event_rows(events)
    postgres_history.append_events(session, rows)
    # A retried batch keeps the first copy.
    postgres_history.append_events(session, rows)
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_session_events").fetchone() == (8,)
        assert connection.execute(
            "SELECT event_id, last_event_id FROM chat_session_events WHERE type = 'delta' ORDER BY event_id"
        ).fetchall() == [(5, 44), (48, 48)]
    recovered = fold_recovery(SessionEvent(last, kind, data) for _f, last, _r, kind, data in rows)
    assert [(event.type, event.data.get("text")) for event in recovered] == [
        ("run_start", None),
        ("reasoning", "Think carefully"),
        ("tool_start", None),
        ("delta", "x" * 40),
        ("optimization", None),
        ("context_usage", None),
        ("delta", "After status"),
    ]
    assert recovered[5].data["used_chars"] == 20


def test_postgres_reset_replaces_the_whole_run_for_a_cursor_inside_a_row(postgres_history):
    session, owner, run, earlier = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    postgres_history.save_session(session, session_state(owner))
    postgres_history.append_events(
        session,
        [
            (1, 1, earlier, "done", {"run_id": earlier}),
            (2, 2, run, "run_start", {"trigger": "user", "run_id": run}),
            (3, 5, run, "delta", {"text": "First middle last", "run_id": run}),
            # Transient progress leaves gaps between stored IDs.
            (90, 90, None, "optimization", {"job_id": "job", "state": "running"}),
        ],
    )
    rows = postgres_history.load_events(session, 4)
    assert [(first, last, kind) for first, last, _run, kind, _data in rows] == [
        (2, 2, "run_start"),
        (3, 5, "delta"),
        (90, 90, "optimization"),
    ]


@pytest.mark.parametrize("typed", [False, True], ids=["production-text", "pr4-typed-snapshot"])
def test_postgres_upgrade_preserves_deployed_sessions_and_message_receipts(uninitialized_postgres_history, typed):
    history = uninitialized_postgres_history
    session, owner, run_id = str(uuid4()), str(uuid4()), str(uuid4())
    migrations = Path(history_module.__file__).with_name("migrations")
    entries = [UserMessage("Original question"), AssistantMessage("Saved answer"), ProposalDecisionEntry("approved")]
    old_state = {
        "schedule_yaml": "description: original",
        "proposal_yaml": "description: proposal",
        "proposal_diff": "Saved diff",
        "dropped_history_messages": 2,
    }
    if typed:
        from nurse_scheduling.ai.transcript import entry_record

        old_state["transcript"] = [{"type": kind, "payload": payload} for kind, payload in map(entry_record, entries)]
    else:
        from nurse_scheduling.ai.context import projected_history

        old_state["history"] = projected_history(entries)
    with history._connect() as connection:
        connection.execute("CREATE TABLE ai_history_migrations (version text PRIMARY KEY)")
        for name in ("001_chat_history.sql", "002_arbitrary_attachments.sql", "003_chat_recovery.sql"):
            connection.execute((migrations / name).read_text(encoding="utf-8"))
            connection.execute("INSERT INTO ai_history_migrations VALUES (%s)", (name,))
        connection.execute(
            "INSERT INTO chat_recovery_sessions (id, owner_hash, expires_at, state, auth_credential_id) "
            "VALUES (%s, %s, to_timestamp(%s), %s, 'team-a')",
            (session, hashlib.sha256(owner.encode()).hexdigest(), time.time() + 3600, json.dumps(old_state)),
        )
        connection.execute(
            "INSERT INTO chat_recovery_turns (id, session_id, request_id, question, model, status) "
            "VALUES (%s, %s, 'accepted-id', 'Original question', 'saved-model', 'completed')",
            (run_id, session),
        )
        connection.execute(
            "INSERT INTO chat_recovery_entries (session_id, channel, turn_id, event_id, last_event_id, event_type, data) "
            "VALUES (%s, %s, %s, 1, 2, 'delta', %s), (%s, 'background', NULL, 1, 1, 'optimization', %s)",
            (
                session,
                run_id,
                run_id,
                json.dumps({"text": "Saved answer"}),
                session,
                json.dumps({"job_id": "saved-job", "state": "completed"}),
            ),
        )
        connection.execute("INSERT INTO chat_recovery_stops VALUES (%s, 'stopped-id')", (session,))
    history.initialize()
    history.initialize()
    restored = history.load_session(session, owner)
    assert restored["entries"] == entries
    assert restored["state"] == {
        "schedule_yaml": "description: original",
        "pending_proposal": {"schedule_yaml": "description: proposal", "diff": "Saved diff", "run_id": None},
        "dropped_history_messages": 2,
        "dropped_entries": 0,
    }
    assert history.find_message(session, "accepted-id") == (run_id, "Original question")
    assert history.message_stopped(session, "stopped-id")
    assert history.load_session(session, str(uuid4())) is None
    events = history.load_events(session, 0)
    assert [(row[3], row[4].get("text")) for row in events] == [("delta", "Saved answer"), ("optimization", None)]
    assert events[0][4]["run_id"] == run_id
    with history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (4,)
        assert connection.execute("SELECT auth_credential_id FROM chat_sessions").fetchone() == ("team-a",)
        assert connection.execute("SELECT model FROM chat_runs").fetchone() == ("saved-model",)


def test_postgres_recovery_enforces_owner_and_session_expiry(postgres_history):
    owner, other_owner = str(uuid4()), str(uuid4())
    expired, current = str(uuid4()), str(uuid4())
    for session, expires_in in ((expired, -1), (current, 60)):
        run = str(uuid4())
        postgres_history.save_session(session, session_state(owner, expires_in))
        postgres_history.start_run(
            run, session, session_state(owner, expires_in), "Original question", 0, model="model", attachment_count=0
        )
        postgres_history.append_events(session, [(1, 1, run, "delta", {"text": "Private answer", "run_id": run})])
    assert postgres_history.load_session(current, other_owner) is None
    assert postgres_history.load_session(expired, owner) is None
    assert postgres_history.load_session(current, owner) is not None
    with postgres_history._connect() as connection:
        connection.execute("UPDATE chat_sessions SET created_at = now() - interval '35 days' WHERE id = %s", (current,))
        connection.execute(
            "UPDATE chat_runs SET started_at = now() - interval '35 days' WHERE session_id = %s", (current,)
        )
    # Retention follows renewed session expiry, rather than individual message age.
    postgres_history.prune()
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM chat_runs").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM chat_session_entries").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM chat_session_events").fetchone() == (1,)


def test_postgres_recovery_keeps_operational_metadata(postgres_history):
    class Provider:
        def __init__(self):
            self.calls = 0

        async def stream_events(self, messages, tools=None):
            self.calls += 1
            yield TextDelta("Answer" if self.calls == 1 else "Partial")
            if self.calls == 1:
                yield TokenUsage(2, 3, 5)
            else:
                raise ProviderError("private detail")

    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=Provider())
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        for question in ("First", "Second"):
            response = client.post(f"/sessions/{session}/messages", json={"message": question, "message_id": question})
            assert response.status_code == 200
        owner = client.cookies[basic.OWNER_COOKIE]
    with postgres_history._connect() as connection:
        rows = connection.execute(
            "SELECT message_id, model, status, error_code, usage, auth_credential_id, attachment_count, "
            "started_at, finished_at, committed FROM chat_runs ORDER BY sequence"
        ).fetchall()
        credential, created, owner_hash = connection.execute(
            "SELECT auth_credential_id, created_at, owner_hash FROM chat_sessions"
        ).fetchone()
        assert session_entries(connection) == [
            record(UserMessage("First")),
            record(AssistantMessage("Answer")),
            record(UserMessage("Second")),
            record(AssistantMessage("Partial", "error")),
        ]
        stored_types = {kind for (kind,) in connection.execute("SELECT DISTINCT type FROM chat_session_events")}
    assert rows[0][:5] == (
        "First",
        "test-model",
        "completed",
        None,
        {
            "prompt_tokens": 2,
            "completion_tokens": 3,
            "total_tokens": 5,
            "cached_prompt_tokens": None,
            "reasoning_tokens": 0,
        },
    )
    assert rows[1][:5] == ("Second", "test-model", "failed", "provider_error", None)
    assert credential and created
    assert owner_hash == hashlib.sha256(owner.encode()).hexdigest()
    assert all(row[5] == credential and row[6] == 0 and row[7] <= row[8] for row in rows)
    assert [row[9] for row in rows] == [True, True]
    assert {"run_start", "delta", "done", "error"} <= stored_types
    # Restore keeps the failed question and partial text with an error marker.
    restored = postgres_history.load_session(session, owner)
    assert restored["entries"] == [
        UserMessage("First"),
        AssistantMessage("Answer"),
        UserMessage("Second"),
        AssistantMessage("Partial", "error"),
    ]
    assert "private detail" not in repr(rows)


@pytest.mark.parametrize("failed", [False, True])
def test_postgres_background_run_keeps_metadata_and_event_ownership(postgres_history, failed):
    class Provider:
        async def stream_events(self, messages, tools=None):
            yield TextDelta("Background output")
            yield TokenUsage(1, 2, 3)
            if failed:
                raise ProviderError("private provider detail")

    async def exercise():
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=Provider())
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            await app.state.session_optimizer._on_completion(session_id, "Review the optimizer result.", None)
            return session_id

    session_id = asyncio.run(exercise())
    with postgres_history._connect() as connection:
        row = connection.execute(
            "SELECT id, kind, auth_credential_id, model, status, error_code, usage, finished_at FROM chat_runs"
        ).fetchone()
        assert row[1:6] == (
            "background",
            "legacy",
            "test-model",
            "failed" if failed else "completed",
            "provider_error" if failed else None,
        )
        assert row[6]["total_tokens"] == 3 and row[7] is not None
        assert connection.execute("SELECT DISTINCT run_id FROM chat_session_events").fetchall() == [(row[0],)]
    assert postgres_history.load_events(session_id, 0)[-1][3] == ("error" if failed else "done")


def test_postgres_rejected_question_does_not_shift_trimmed_history_after_restart(postgres_history, monkeypatch):
    settings = basic.make_settings(history_postgres_url="test", max_history_messages=2)
    provider = basic.FakeProvider([["First answer"], ["Latest answer"]])
    app = basic.create_test_app(settings=settings, provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        path = f"/sessions/{session_id}/messages"
        with monkeypatch.context() as patch:
            patch.setattr(ChatHistory, "start_run", unavailable)
            refused = client.post(path, json={"message": "Question", "message_id": "question"})
            assert refused.status_code == 503
        for question in ("Question", "Next question"):
            response = client.post(path, json={"message": question, "message_id": question})
            assert basic.parse_sse(response.text)[-1][0] == "done"
        owner = client.cookies[basic.OWNER_COOKIE]
        session = app.state.session_store._sessions[session_id]
        assert session.dropped_entries == 2
        expected = [UserMessage("Next question"), AssistantMessage("Latest answer")]
        assert session.transcript == expected
    restarted = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(restarted, cookies={basic.OWNER_COOKIE: owner}) as client:
        assert client.get(f"/sessions/{session_id}").status_code == 200
        assert restarted.state.session_store._sessions[session_id].transcript == expected


def test_postgres_recovers_complete_message_and_history_after_backend_restart(postgres_history):
    settings = basic.make_settings(history_postgres_url="test")
    request = {"message": "Original question", "message_id": "stable-question"}
    answer = "FIRST" + "x" * 1200 + "LAST"

    async def first_process():
        app = basic.create_test_app(
            settings=settings, provider=basic.FakeProvider([["FIRST", *(["x"] * 1200), "LAST"]])
        )
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            run_id = (await client.post(f"/sessions/{session_id}/messages", json=request)).json()["run_id"]
            owner = client.cookies[basic.OWNER_COOKIE]
            frames = await read_events(app, session_id, owner)
            return session_id, owner, run_id, frames[-1][0]

    session_id, owner, run_id, cursor = asyncio.run(first_process())
    provider = basic.FakeProvider([["This must never run"]])

    async def restarted_process():
        app = basic.create_test_app(settings=settings, provider=provider)
        async with serving(app) as client:
            assert (await client.get(f"/sessions/{session_id}")).status_code == 404
            client.cookies.set(basic.OWNER_COOKIE, owner)
            assert (await client.get(f"/sessions/{session_id}")).status_code == 200
            repeated = await client.post(f"/sessions/{session_id}/messages", json=request)
            assert repeated.json() == {"run_id": run_id}
            # The browser cursor is from the previous process, so the reset replaces the run.
            frames = await read_events(app, session_id, owner, cursor, until="session_reset")
            return frames, app.state.session_store._sessions[session_id].transcript

    frames, transcript = asyncio.run(restarted_process())
    assert reset_text(frames) == answer
    assert provider.calls == []
    assert transcript == [UserMessage("Original question"), AssistantMessage(answer)]


def test_postgres_recovers_question_and_partial_output_from_interrupted_run(postgres_history):
    session, run, owner = str(uuid4()), str(uuid4()), str(uuid4())
    postgres_history.save_session(session, session_state(owner))
    postgres_history.start_run(
        run,
        session,
        session_state(owner),
        "Keep working",
        0,
        model="model",
        attachment_count=0,
        message_id="interrupted-question",
    )
    postgres_history.append_events(
        session,
        [
            (1, 1, run, "run_start", {"trigger": "user", "run_id": run}),
            (2, 2, run, "delta", {"text": "Saved partial output", "run_id": run}),
        ],
    )
    provider = basic.FakeProvider()

    async def exercise():
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
        async with serving(app, owner) as client:
            response = await client.post(
                f"/sessions/{session}/messages", json={"message": "Keep working", "message_id": "interrupted-question"}
            )
            assert response.json() == {"run_id": run}
            frames = await read_events(app, session, owner, 1, until="session_reset")
            assert app.state.session_store._sessions[session].history == [
                {"role": "user", "content": "Keep working"},
                {"role": "assistant", "content": basic.ABORTED_RESPONSE_HISTORY},
            ]
            return frames

    frames = asyncio.run(exercise())
    (reset,) = [data for _id, kind, data in frames if kind == "session_reset"]
    assert reset_text(frames) == "Saved partial output"
    assert reset["events"][-1]["type"] == "error"
    assert "service restarted" in reset["events"][-1]["data"]["message"]
    assert provider.calls == []
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, error_code FROM chat_runs").fetchone() == (
            "failed",
            "service_restart",
        )


def test_postgres_recovers_background_metadata_after_restart(postgres_history):
    session, owner, run = str(uuid4()), str(uuid4()), str(uuid4())
    postgres_history.save_session(session, session_state(owner), "team-a")
    postgres_history.start_run(
        run, session, session_state(owner), "Review result", 0, model="model", attachment_count=0, kind="background"
    )
    postgres_history.append_events(
        session,
        [
            (1, 1, run, "run_start", {"trigger": "optimizer", "run_id": run}),
            (2, 2, run, "delta", {"text": "Saved background output", "run_id": run}),
        ],
    )
    provider = basic.FakeProvider()

    async def exercise():
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
        async with serving(app, owner) as client:
            assert (await client.get(f"/sessions/{session}")).status_code == 200

    asyncio.run(exercise())
    assert provider.calls == []
    with postgres_history._connect() as connection:
        assert connection.execute(
            "SELECT kind, auth_credential_id, model, status, error_code FROM chat_runs"
        ).fetchone() == ("background", "team-a", "model", "failed", "service_restart")
    events = fold_recovery(
        SessionEvent(last, kind, data) for _f, last, _r, kind, data in postgres_history.load_events(session, 0)
    )
    assert [event.type for event in events] == ["run_start", "delta", "error"]
    assert "background response" in events[-1].data["message"]


def test_postgres_reset_loads_complete_output_after_projection_eviction(postgres_history):
    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"),
            provider=basic.FakeProvider([["First ", "middle ", "last"]]),
        )
        # A tiny replay budget evicts output from both the journal and the projection.
        app.state.session_event_stream._max_bytes = 200
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            await client.post(f"/sessions/{session_id}/messages", json={"message": "Long answer"})
            while app.state.runs.busy(session_id):
                await asyncio.sleep(0.01)
            owner = client.cookies[basic.OWNER_COOKIE]
            return await read_events(app, session_id, owner, 0, until="session_reset")

    frames = asyncio.run(exercise())
    (reset,) = [data for _id, kind, data in frames if kind == "session_reset"]
    assert reset["incomplete"] is False
    assert reset_text(frames) == "First middle last"
    assert reset["events"][-1]["type"] == "done"


def test_postgres_evicted_session_restores_on_its_next_request(postgres_history):
    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test", max_sessions=1),
            provider=basic.FakeProvider([["Saved answer"]]),
        )
        async with serving(app) as client:
            first = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            await client.post(f"/sessions/{first}/messages", json={"message": "Question"})
            while app.state.runs.busy(first):
                await asyncio.sleep(0.01)
            await app.state.recovery.flush(first)
            second = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            assert list(app.state.session_store._sessions) == [second]
            assert (await client.get(f"/sessions/{first}")).status_code == 200
            assert list(app.state.session_store._sessions) == [first]
            return app.state.session_store._sessions[first].transcript

    assert asyncio.run(exercise()) == [UserMessage("Question"), AssistantMessage("Saved answer")]


def test_postgres_restored_conversation_matches_the_live_conversation(postgres_history):
    settings = basic.make_settings(history_postgres_url="test", max_history_messages=4)
    provider = basic.FakeProvider([["A1"], ProviderError("private detail"), ["A3"], ["A4"]])
    app = basic.create_test_app(settings=settings, provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        client.post(f"/sessions/{session_id}/messages", json={"message": "Q1"})
        basic.upload_files(client, session_id, ("ward.xlsx", b"bytes", "application/octet-stream"))
        payload = basic.base_schedule_payload()
        payload["description"] = "Ward A"
        path = f"/sessions/{session_id}/schedule"
        assert client.put(path, json={"schedule_yaml": basic.schedule_yaml(payload)}).status_code == 204
        for question in ("Q2", "Q3", "Q4"):
            client.post(f"/sessions/{session_id}/messages", json={"message": question})
        owner = client.cookies[basic.OWNER_COOKIE]
        live = app.state.session_store._sessions[session_id]
        expected = (list(live.transcript), live.dropped_entries, live.dropped_history_messages)
    # Retention trimmed the first exchange, both app events, and the interrupted second exchange.
    assert expected == ([UserMessage("Q3"), AssistantMessage("A3"), UserMessage("Q4"), AssistantMessage("A4")], 6, 6)

    async def restarted():
        app = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
        async with serving(app, owner) as client:
            assert (await client.get(f"/sessions/{session_id}")).status_code == 200
            restored = app.state.session_store._sessions[session_id]
            return list(restored.transcript), restored.dropped_entries, restored.dropped_history_messages

    assert asyncio.run(restarted()) == expected


def test_postgres_saves_each_message_before_its_run_ends(postgres_history):
    class Provider:
        def __init__(self):
            self.calls = 0

        async def stream_events(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                for event in basic.rename_call():
                    yield event
                return
            yield TextDelta("Still working")
            await asyncio.Event().wait()

    def saved_types():
        with postgres_history._connect() as connection:
            return [kind for kind, _payload in session_entries(connection)]

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test", max_schedule_bytes=basic.SCHEDULE_BYTE_LIMIT),
            provider=Provider(),
            sandbox_factory=basic.rename_factory(),
        )
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            await client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})
            deadline = time.monotonic() + 5
            while len(saved := await asyncio.to_thread(saved_types)) < 3 and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            # A crash now would keep the finished tool call and its result.
            assert app.state.runs.busy(session_id)
            return saved

    assert asyncio.run(exercise()) == ["user", "assistant", "tool_result"]


def test_postgres_stop_before_message_arrival_survives_restart(postgres_history):
    settings = basic.make_settings(history_postgres_url="test")
    first = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(first) as client:
        session = basic.create_session(client)
        owner = client.cookies[basic.OWNER_COOKIE]
        assert client.post(f"/sessions/{session}/stop", json={"message_id": "stopped-request"}).status_code == 202
    provider = basic.FakeProvider()

    async def exercise():
        app = basic.create_test_app(settings=settings, provider=provider)
        async with serving(app, owner) as client:
            result = await client.post(
                f"/sessions/{session}/messages", json={"message": "Original question", "message_id": "stopped-request"}
            )
            assert result.status_code == 202
            frames = await read_events(app, session, owner, until="stopped")
            return frames, app.state.session_store._sessions[session].transcript

    frames, transcript = asyncio.run(exercise())
    assert frames[-1][1] == "stopped"
    assert provider.calls == []
    assert transcript == [UserMessage("Original question"), AssistantMessage("", "aborted")]

    restored_provider = basic.FakeProvider()
    restored = basic.create_test_app(settings=settings, provider=restored_provider)
    with basic.AuthenticatedTestClient(restored) as client:
        client.cookies.set(basic.OWNER_COOKIE, owner)
        response = client.post(f"/sessions/{session}/messages", json={"message": "Retry"})
        assert basic.parse_sse(response.text)[-1][0] == "done"
        assert restored_provider.calls[0][1:3] == [
            {"role": "user", "content": "Original question"},
            {"role": "assistant", "content": basic.ABORTED_RESPONSE_HISTORY},
        ]


@pytest.mark.parametrize("kind", ["foreground", "background"])
def test_postgres_shutdown_reports_interrupted_run_as_restart(postgres_history, kind):
    started = asyncio.Event()

    class WaitingProvider:
        async def stream_events(self, messages, tools=None):
            yield TextDelta("Saved partial output")
            started.set()
            await asyncio.Event().wait()

    settings = basic.make_settings(history_postgres_url="test")

    async def exercise():
        app = basic.create_test_app(settings=settings, provider=WaitingProvider())
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            if kind == "foreground":
                await client.post(f"/sessions/{session_id}/messages", json={"message": "Q", "message_id": "m"})
            else:
                optimizer = app.state.session_optimizer
                task = asyncio.create_task(optimizer._on_completion(session_id, "Review the optimizer result.", None))
                optimizer._tasks.add(task)
            await asyncio.wait_for(started.wait(), timeout=5)
            # Let the output reach storage before the graceful shutdown.
            await asyncio.sleep(0.1)
            return session_id, client.cookies[basic.OWNER_COOKIE]

    session_id, owner = asyncio.run(exercise())

    async def restarted():
        app = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
        async with serving(app, owner) as client:
            if kind == "foreground":
                response = await client.post(
                    f"/sessions/{session_id}/messages", json={"message": "Q", "message_id": "m"}
                )
                assert response.status_code == 202
            else:
                assert (await client.get(f"/sessions/{session_id}")).status_code == 200
            return await read_events(app, session_id, owner, until="session_reset")

    frames = asyncio.run(restarted())
    (reset,) = [data for _id, event, data in frames if event == "session_reset"]
    assert reset_text(frames) == "Saved partial output"
    assert reset["events"][-1]["type"] == "error"
    assert "service restarted" in reset["events"][-1]["data"]["message"]
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, error_code FROM chat_runs").fetchone() == (
            "failed",
            "service_restart",
        )


def test_postgres_retries_a_final_outcome_that_failed_to_save(postgres_history, monkeypatch):
    settings = basic.make_settings(history_postgres_url="test")
    request = {"message": "Question", "message_id": "unsaved-outcome"}
    first = basic.create_test_app(settings=settings, provider=basic.FakeProvider([["Saved answer"]]))
    with basic.AuthenticatedTestClient(first) as client:
        session_id = basic.create_session(client)
        with monkeypatch.context() as patch:
            patch.setattr(ChatHistory, "finish_run", unavailable)
            response = client.post(f"/sessions/{session_id}/messages", json=request)
        assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
        update = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": basic.schedule_yaml()})
        assert update.status_code == 204
        owner = client.cookies[basic.OWNER_COOKIE]
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_runs").fetchone() == ("completed",)
    provider = basic.FakeProvider([["This must never run"]])

    async def restarted():
        app = basic.create_test_app(settings=settings, provider=provider)
        async with serving(app, owner) as client:
            assert (await client.post(f"/sessions/{session_id}/messages", json=request)).status_code == 202
            return await read_events(app, session_id, owner, until="session_reset")

    frames = asyncio.run(restarted())
    (reset,) = [data for _id, kind, data in frames if kind == "session_reset"]
    assert reset_text(frames) == "Saved answer"
    assert "service restarted" not in json.dumps(reset)
    assert provider.calls == []


def test_postgres_shutdown_retries_a_failed_final_outcome(postgres_history, monkeypatch):
    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider([["Saved answer"]])
        )
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            with monkeypatch.context() as patch:
                patch.setattr(ChatHistory, "finish_run", unavailable)
                await client.post(
                    f"/sessions/{session_id}/messages", json={"message": "Question", "message_id": "accepted"}
                )
                while app.state.runs.busy(session_id):
                    await asyncio.sleep(0.01)
                await app.state.recovery.flush(session_id)
            owner = client.cookies[basic.OWNER_COOKIE]
        return session_id, owner

    session_id, owner = asyncio.run(exercise())
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, committed FROM chat_runs").fetchone() == ("completed", True)
    assert postgres_history.load_session(session_id, owner)["entries"] == [
        UserMessage("Question"),
        AssistantMessage("Saved answer"),
    ]


def test_postgres_restart_recovers_a_saved_terminal_with_an_unfinished_status(postgres_history):
    session_id, owner, run_id = str(uuid4()), str(uuid4()), str(uuid4())
    state = session_state(owner)
    postgres_history.save_session(session_id, state)
    postgres_history.start_run(
        run_id, session_id, state, "Question", 0, model="model", attachment_count=0, message_id="accepted"
    )
    postgres_history.append_entries(session_id, [(1, run_id, AssistantMessage("Saved answer"))])
    postgres_history.append_events(session_id, [(1, 1, run_id, "done", {"run_id": run_id, "history_saved": False})])

    async def restarted():
        provider = basic.FakeProvider([["Must not execute"]])
        app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
        async with serving(app, owner) as client:
            response = await client.post(
                f"/sessions/{session_id}/messages", json={"message": "Question", "message_id": "accepted"}
            )
            assert response.json() == {"run_id": run_id}
            assert provider.calls == []
            assert app.state.session_store._sessions[session_id].transcript == [
                UserMessage("Question"),
                AssistantMessage("Saved answer"),
            ]

    asyncio.run(restarted())
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, committed FROM chat_runs").fetchone() == ("completed", True)
        assert connection.execute("SELECT count(*) FROM chat_session_events WHERE type = 'done'").fetchone() == (1,)


def test_postgres_explicit_reset_recovers_output_at_the_current_cursor(postgres_history):
    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"),
            provider=basic.FakeProvider([["Complete answer"]]),
        )
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            await client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
            while app.state.runs.busy(session_id):
                await asyncio.sleep(0.01)
            cursor = app.state.session_event_stream.cursor(session_id)
            frames = await read_events(
                app, session_id, client.cookies[basic.OWNER_COOKIE], cursor, until="session_reset", reset=True
            )
            assert reset_text(frames) == "Complete answer"
            assert frames[0][2]["events"][-1]["type"] == "done"

    asyncio.run(exercise())


def test_reset_covers_output_when_the_run_finishes_during_its_storage_read(postgres_history, monkeypatch):
    captured = threading.Event()
    return_rows = threading.Event()
    original_load = ChatHistory.load_events

    def delayed_load(self, session_id, after_id):
        rows = original_load(self, session_id, after_id)
        captured.set()
        assert return_rows.wait(5)
        return rows

    async def scenario():
        started = asyncio.Event()
        complete = asyncio.Event()

        class WaitingProvider:
            async def stream_events(self, messages, tools=None):
                yield TextDelta("Partial answer")
                started.set()
                await complete.wait()
                yield TextDelta(" completed")

        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=WaitingProvider()
        )
        app.state.session_event_stream._max_bytes = 1
        async with serving(app) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            run_id = (
                await client.post(
                    f"/sessions/{session_id}/messages", json={"message": "Question", "message_id": "accepted"}
                )
            ).json()["run_id"]
            await asyncio.wait_for(started.wait(), 5)
            await asyncio.sleep(0.05)
            await app.state.recovery.flush(session_id)
            monkeypatch.setattr(ChatHistory, "load_events", delayed_load)
            reader = asyncio.create_task(
                read_events(app, session_id, client.cookies[basic.OWNER_COOKIE], until="session_reset", reset=True)
            )
            assert await asyncio.to_thread(captured.wait, 5)
            complete.set()
            while app.state.runs.busy(session_id):
                await asyncio.sleep(0.01)
            await app.state.recovery.flush(session_id)
            return_rows.set()
            frames = await reader
            first = next(data for _id, kind, data in frames if kind == "session_reset")
            assert first["active_run_id"] is None
            assert any(event["data"].get("run_id") == run_id for event in first["events"])
            assert not any(event["type"] == "done" for event in first["events"])
            current = await read_events(
                app, session_id, client.cookies[basic.OWNER_COOKIE], until="session_reset", reset=True
            )
            latest = next(data for _id, kind, data in current if kind == "session_reset")
            assert any(event["type"] == "done" and event["data"].get("run_id") == run_id for event in latest["events"])

    try:
        asyncio.run(scenario())
    finally:
        return_rows.set()
