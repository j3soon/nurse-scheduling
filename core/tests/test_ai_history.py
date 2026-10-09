"""AI recovery lifecycle and PostgreSQL persistence checks."""

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
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql

from nurse_scheduling.ai import history as history_module
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.history import ChatHistory
from nurse_scheduling.ai.provider import ProviderError, TextDelta, TokenUsage

from . import test_ai_basic as basic


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

    provider = Provider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        for question in ("First", "Second"):
            response = client.post(f"/sessions/{session}/messages", json={"message": question, "message_id": question})
            assert response.status_code == 200
        owner = client.cookies[basic.OWNER_COOKIE]
        with postgres_history._connect() as connection:
            rows = connection.execute(
                "SELECT question, model, status, error_code, usage, auth_credential_id, attachment_count, "
                "started_at, finished_at FROM chat_recovery_turns ORDER BY sequence"
            ).fetchall()
            credential, created = connection.execute(
                "SELECT auth_credential_id, created_at FROM chat_recovery_sessions"
            ).fetchone()
            assert connection.execute("SELECT to_regclass('chat_turns'), to_regclass('chat_sessions')").fetchone() == (
                None,
                None,
            )
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
        assert all(row[5] == credential and row[6] == 0 and row[7] <= row[8] for row in rows)
        assert postgres_history.load_recovery_session(session, owner)["state"]["history"][-1]["content"] == "Answer"
        assert "private detail" not in repr(rows)


@pytest.mark.parametrize("failed", [False, True])
def test_postgres_background_turn_keeps_metadata_and_entry_ownership(postgres_history, failed):
    from nurse_scheduling.ai.background import run_background_turn
    from nurse_scheduling.ai.lifecycle import Turn

    class Provider:
        async def stream_events(self, messages, tools=None):
            yield TextDelta("Background output")
            yield TokenUsage(1, 2, 3)
            if failed:
                raise ProviderError("private provider detail")

    async def exercise():
        settings = basic.make_settings(history_postgres_url="test")
        provider = Provider()
        app = basic.create_test_app(settings=settings, provider=provider)
        store = app.state.session_store
        session = store.create(str(uuid4()), basic.schedule_yaml())
        postgres_history.save_recovery_session(session.id, *store.recovery_state(session.id), "team-a")
        await run_background_turn(
            session.id,
            "Review optimizer result",
            None,
            settings=settings,
            store=store,
            event_broker=app.state.session_event_broker,
            turn=Turn(),
            concurrency_limit=asyncio.Semaphore(1),
            history_log=postgres_history,
            provider=provider,
            sandbox_factory=app.state.sandbox_factory,
            session_optimizer=app.state.session_optimizer,
        )
        with postgres_history._connect() as connection:
            row = connection.execute(
                "SELECT id, kind, auth_credential_id, model, status, error_code, usage, finished_at FROM chat_recovery_turns"
            ).fetchone()
            assert row[1:6] == (
                "background",
                "team-a",
                "test-model",
                "failed" if failed else "completed",
                "provider_error" if failed else None,
            )
            assert row[6]["total_tokens"] == 3 and row[7] is not None
            assert connection.execute("SELECT DISTINCT turn_id FROM chat_recovery_entries").fetchall() == [(row[0],)]
        record = postgres_history.load_recovery_session(session.id, session.owner_token)
        assert record["background_status"] == row[4]
        assert record["turns"] == []
        assert any(
            event["type"] == "delta" and event["data"] == {"text": "Background output", "turn_id": str(row[0])}
            for event in record["background_events"]
        )

    asyncio.run(exercise())


@pytest.fixture
def recorded_history(monkeypatch):
    records = {"starts": [], "finishes": []}
    monkeypatch.setattr(ChatHistory, "initialize", lambda _self: None)
    monkeypatch.setattr(ChatHistory, "start_recovery_turn", lambda _self, *args: records["starts"].append(args))
    monkeypatch.setattr(ChatHistory, "finish_recovery_turn", lambda _self, *args: records["finishes"].append(args))
    for operation in (
        "save_recovery_session",
        "append_recovery_event",
        "load_recovery_turn",
        "stop_recovery_request",
        "recovery_request_stopped",
    ):
        monkeypatch.setattr(ChatHistory, operation, lambda *_args: None)
    return records


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
    assert start[1:4] == (session_id, start[2], "Question")
    assert start[4]["model"] == "test-model"
    assert finish[4] == start[0]
    assert finish[6] == ("error" if failed else "done")
    assert finish[8] == {
        "error_code": "provider_error" if failed else None,
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
            "cached_prompt_tokens": None,
            "reasoning_tokens": 0,
        },
    }
    if not failed:
        assert basic.parse_sse(response.text)[-1] == ("done", {"message_id": start[0], "history_saved": True})
    assert "private provider credential" not in repr(recorded_history)


def test_database_unavailable_releases_session_before_provider_call(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "start_recovery_turn", unavailable)
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
        assert response.status_code == 503
        assert provider.calls == []
        monkeypatch.setattr(ChatHistory, "start_recovery_turn", lambda *_args: None)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})
        assert basic.parse_sse(response.text)[-1][0] == "done"


def test_stop_during_failed_turn_start_does_not_stop_next_turn(recorded_history, monkeypatch):
    release = threading.Event()
    calls = []

    def save(*_args):
        calls.append(None)
        if len(calls) == 2:
            release.wait(5)
            raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "save_recovery_session", save)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            first = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "First"}))
            while len(calls) < 2:
                await asyncio.sleep(0.01)
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            release.set()
            assert (await first).status_code == 503
            second = await client.post(f"/sessions/{session_id}/messages", json={"message": "Second"})
            return basic.parse_sse(second.text)[-1][0]

    assert asyncio.run(exercise()) == "done"


def test_failed_session_save_releases_the_session_slot(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "save_recovery_session", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        response = client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})
    assert response.status_code == 503
    assert app.state.session_store._sessions == {}
    assert app.state.session_store.retained_bytes == 0


def test_recovery_read_failure_during_message_lookup_returns_503(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "load_recovery_turn", unavailable)
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question", "message_id": "m1"})
    assert response.status_code == 503
    assert provider.calls == []


def test_cancelled_turn_admission_releases_the_session(recorded_history, monkeypatch):
    blocked = threading.Event()
    release = threading.Event()
    calls = []

    def save(*_args):
        calls.append(None)
        if len(calls) == 2:
            blocked.set()
            release.wait(5)

    monkeypatch.setattr(ChatHistory, "save_recovery_session", save)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            first = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "First"}))
            await asyncio.to_thread(blocked.wait, 5)
            first.cancel()
            release.set()
            await asyncio.gather(first, return_exceptions=True)
            assert not app.state.session_store._sessions[session_id].active
            assert not app.state.turns.busy(session_id)
            second = await client.post(f"/sessions/{session_id}/messages", json={"message": "Second"})
            return basic.parse_sse(second.text)[-1][0]

    assert asyncio.run(exercise()) == "done"


def test_recovery_state_writes_commit_in_capture_order(recorded_history, monkeypatch):
    older, newer = "description: older", "description: newer"
    blocked = threading.Event()
    release = threading.Event()
    committed = []

    def save(_self, _session_id, _owner, _expires_at, state, _credential_id=None):
        if state["schedule_yaml"] == older:
            blocked.set()
            release.wait(5)
        committed.append(state["schedule_yaml"])

    monkeypatch.setattr(ChatHistory, "save_recovery_session", save)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
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

    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "save_recovery_session", unavailable)
    body = {"base_sha256": revision} if decision == "approve" else None
    response = client.post(f"/sessions/{session_id}/proposal/{decision}", json=body)
    assert response.status_code == 200
    assert response.json()["history_saved"] is False
    assert not client.app.state.session_store._sessions[session_id].proposal_yaml


def test_schedule_update_that_cannot_be_saved_can_be_retried(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        path = f"/sessions/{session_id}/schedule"
        monkeypatch.setattr(ChatHistory, "save_recovery_session", unavailable)
        assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 503
        monkeypatch.setattr(ChatHistory, "save_recovery_session", lambda *_args: None)
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
            store.begin(session_id, store._sessions[session_id].owner_token)
        assert client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()}).status_code == 429
        for session_id in (first, second):
            store.abort(session_id, store._sessions[session_id].turn)
        assert client.get(f"/sessions/{first}/uploads").status_code == 200
        third = basic.create_session(client)
    assert list(store._sessions) == [first, third]


@pytest.mark.parametrize("operation", ["finish_recovery_turn", "save_recovery_session"])
def test_full_store_keeps_a_session_until_its_state_write_ends(recorded_history, monkeypatch, operation):
    blocked = threading.Event()
    release = threading.Event()

    def write(*_args):
        blocked.set()
        release.wait(5)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test", max_sessions=1), provider=basic.FakeProvider()
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            monkeypatch.setattr(ChatHistory, operation, write)
            if operation == "finish_recovery_turn":
                request = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
            else:
                request = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": "description: newer"})
            pending = asyncio.create_task(request)
            await asyncio.to_thread(blocked.wait, 5)
            # The session is idle while its write runs, but eviction would make the write fail.
            assert app.state.session_store._sessions[session_id].active is False
            assert (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).status_code == 429
            release.set()
            response = await pending
            if operation == "finish_recovery_turn":
                assert basic.parse_sse(response.text)[-1][0] == "done"
            else:
                assert response.status_code == 204
            await asyncio.wait_for(
                asyncio.gather(*(turn.done for pending in app.state.turns._turns.values() for turn in pending)),
                timeout=1,
            )
            assert (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).status_code == 201

    asyncio.run(exercise())


@pytest.mark.parametrize("operation", ["finish_recovery_turn", "save_recovery_session"])
def test_full_store_keeps_a_session_whose_state_was_not_saved(recorded_history, monkeypatch, operation):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test", max_sessions=1), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        path = f"/sessions/{session_id}/schedule"
        with monkeypatch.context() as patch:
            patch.setattr(ChatHistory, operation, unavailable)
            if operation == "finish_recovery_turn":
                response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
                assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
            else:
                assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 503
        # Memory holds the only copy of the newest state until a save succeeds.
        assert client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()}).status_code == 429
        assert client.put(path, json={"schedule_yaml": "description: newer"}).status_code == 204
        basic.create_session(client)
    assert session_id not in app.state.session_store._sessions
    if operation == "finish_recovery_turn":
        # The schedule save also retried the answer's final outcome with the newer state.
        [retried] = recorded_history["finishes"]
        assert retried[3]["schedule_yaml"] == "description: newer"
        assert retried[6:8] == ("done", {"message_id": retried[4], "history_saved": True})


def test_postgres_retries_a_final_outcome_that_failed_to_save(postgres_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    settings = basic.make_settings(history_postgres_url="test")
    request = {"message": "Question", "message_id": "unsaved-outcome"}
    first = basic.create_test_app(settings=settings, provider=basic.FakeProvider([["Saved answer"]]))
    with basic.AuthenticatedTestClient(first) as client:
        session_id = basic.create_session(client)
        with monkeypatch.context() as patch:
            patch.setattr(ChatHistory, "finish_recovery_turn", unavailable)
            response = client.post(f"/sessions/{session_id}/messages", json=request)
        assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
        update = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": basic.schedule_yaml()})
        assert update.status_code == 204
        cookies = dict(client.cookies)
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_recovery_turns").fetchone() == ("completed",)
    provider = basic.FakeProvider([["This must never run"]])
    restarted = basic.create_test_app(settings=settings, provider=provider)
    with basic.AuthenticatedTestClient(restarted) as client:
        client.cookies.update(cookies)
        response = client.post(f"/sessions/{session_id}/messages", json=request)
    [(kind, snapshot)] = basic.parse_sse(response.text, include_model_input=True)
    assert kind == "turn_snapshot"
    assert "Saved answer" in response.text
    assert "service restarted" not in response.text
    assert snapshot["events"][-1]["type"] == "done"
    assert snapshot["events"][-1]["data"]["history_saved"] is True
    assert provider.calls == []


def test_full_store_without_recovery_keeps_refusing_new_sessions():
    app = basic.create_test_app(settings=basic.make_settings(max_sessions=1), provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(app) as client:
        basic.create_session(client)
        response = client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})
    assert response.status_code == 429


def test_final_write_failure_preserves_successful_conversation(recorded_history, monkeypatch, caplog):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "finish_recovery_turn", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
    assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
    assert "AI history finish_recovery_turn failed" in caplog.text
    assert "secret-database-url" not in caplog.text


@pytest.mark.parametrize("failing", [("append_recovery_event",), ("start_recovery_turn", "finish_recovery_turn")])
def test_background_recovery_outage_releases_session_and_reports_status(recorded_history, monkeypatch, failing):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    for operation in (*failing, "save_recovery_session"):
        monkeypatch.setattr(ChatHistory, operation, unavailable)

    async def exercise():
        app = basic.create_test_app(
            settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
        )
        session = app.state.session_store.create(str(uuid4()), basic.schedule_yaml())
        optimizer = app.state.session_optimizer
        await optimizer._on_update(session.id, {"job_id": "job", "state": "completed", "terminal": True})
        await optimizer._on_completion(session.id, "Optimizer finished", None)
        events = app.state.session_event_broker.events_after(session.id)
        return [event.type for event in events], app.state.session_store._sessions[session.id].active

    event_types, active = asyncio.run(exercise())
    assert event_types[0] == "optimization"
    assert event_types[-1] == "error"
    assert not active


def test_database_unavailable_prevents_startup(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret")

    monkeypatch.setattr(ChatHistory, "initialize", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with pytest.raises(RuntimeError, match="database initialization failed"), basic.AuthenticatedTestClient(app):
        pass


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


def test_postgres_recovery_combines_fragments_without_losing_boundaries(postgres_history):
    history = postgres_history
    session, owner, turn = str(uuid4()), str(uuid4()), str(uuid4())
    history.save_recovery_session(session, owner, time.time() + 60, {})
    history.start_recovery_turn(turn, session, "request", "Question")
    history.append_recovery_event(session, turn, 1, "reasoning", {"text": "Think "})
    history.append_recovery_event(session, turn, 2, "reasoning", {"text": "carefully"})
    history.append_recovery_event(session, turn, 3, "tool_start", {"name": "read"})
    for cursor in range(4, 44):
        history.append_recovery_event(session, turn, cursor, "delta", {"text": "x"})
    history.append_recovery_event(session, turn, 43, "delta", {"text": "duplicate"})
    history.append_recovery_event(session, turn, 44, "context_usage", {"tokens": 10})
    history.append_recovery_event(session, turn, 45, "context_usage", {"tokens": 20})
    history.append_recovery_event(session, "background", 1, "turn_start", {"message_id": "background"})
    history.append_recovery_event(session, "background", 2, "delta", {"text": "Background "})
    history.append_recovery_event(session, "background", 3, "delta", {"text": "answer"})
    history.append_recovery_event(session, turn, 46, "delta", {"text": "After background"})
    with history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_recovery_entries").fetchone() == (7,)
    recovered = history.load_recovery_turn(session, "request")
    assert [(event["id"], event["type"], event["data"]) for event in recovered["events"]] == [
        (2, "reasoning", {"text": "Think carefully"}),
        (3, "tool_start", {"name": "read"}),
        (43, "delta", {"text": "x" * 40}),
        (45, "context_usage", {"tokens": 20}),
        (46, "delta", {"text": "After background"}),
    ]
    with history._connect() as connection:
        assert connection.execute("SELECT channel FROM chat_recovery_entries ORDER BY sequence").fetchall() == [
            (turn,),
            (turn,),
            (turn,),
            (turn,),
            ("background",),
            ("background",),
            (turn,),
        ]


@pytest.mark.parametrize("channel", ["foreground", "background"])
def test_postgres_restored_stream_replaces_output_for_cursor_inside_entry(postgres_history, channel):
    from nurse_scheduling.ai.background import SessionEventBroker
    from nurse_scheduling.ai.turns import TurnJournal

    async def exercise():
        session, owner, turn = str(uuid4()), str(uuid4()), str(uuid4())
        postgres_history.save_recovery_session(session, owner, time.time() + 60, {})
        postgres_history.start_recovery_turn(turn, session, "request", "Question")
        stored_channel = turn if channel == "foreground" else "background"
        for cursor, text in enumerate(("First ", "middle ", "last"), 1):
            postgres_history.append_recovery_event(session, stored_channel, cursor, "delta", {"text": text})
        if channel == "foreground":
            recovered = await TurnJournal(postgres_history).get(session, "request")
            stream = recovered.stream(2)
            cursor, kind, data = await anext(stream)
        else:
            broker = SessionEventBroker()
            broker.load_snapshot = lambda sid: postgres_history.read("load_background_snapshot", sid)
            broker.restore(session, postgres_history.load_recovery_session(session, owner)["background_events"])
            stream = broker.stream(session, 2)
            event = await anext(stream)
            cursor, kind, data = event.id, event.type, event.data
        await stream.aclose()
        assert kind == ("turn_snapshot" if channel == "foreground" else "session_snapshot")
        assert cursor == 3
        assert data["events"] == [{"type": "delta", "data": {"text": "First middle last"}}]

    asyncio.run(exercise())


def test_postgres_upgrade_discards_audit_rows(uninitialized_postgres_history):
    history = uninitialized_postgres_history
    session, owner = str(uuid4()), str(uuid4())
    with history._connect() as connection:
        connection.execute("CREATE TABLE ai_history_migrations (version text PRIMARY KEY)")
        for migration in sorted(Path(history_module.__file__).with_name("migrations").glob("00[1-2]*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO ai_history_migrations VALUES (%s)", (migration.name,))
        connection.execute("INSERT INTO chat_sessions (id, auth_credential_id) VALUES (%s, 'team-a')", (session,))
        connection.execute(
            "INSERT INTO chat_turns (id, session_id, user_message, model) VALUES (%s, %s, 'Old audit text', 'model')",
            (str(uuid4()), session),
        )
    history.initialize()
    history.initialize()
    with history._connect() as connection:
        assert connection.execute("SELECT to_regclass('chat_turns'), to_regclass('chat_sessions')").fetchone() == (
            None,
            None,
        )
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (3,)
        assert connection.execute("SELECT count(*) FROM chat_recovery_sessions").fetchone() == (0,)
    history.save_recovery_session(session, owner, time.time() + 60, {}, "team-a")
    history.start_recovery_turn(str(uuid4()), session, "request", "New question", {"model": "model"})
    assert history.load_recovery_session(session, owner)["turns"][0]["question"] == "New question"


@pytest.mark.parametrize("channel", ["foreground", "background"])
@pytest.mark.parametrize(
    "terminal, status", [("done", "completed"), ("error", "failed"), ("stopped", "cancelled"), ("stale", "stale")]
)
def test_postgres_recovery_commits_status_context_and_output_together(postgres_history, channel, terminal, status):
    history = postgres_history
    session, owner, turn = str(uuid4()), str(uuid4()), str(uuid4())
    expiry = time.time() + 60
    history.save_recovery_session(session, owner, expiry, {})
    stored_channel = turn if channel == "foreground" else "background"
    history.start_recovery_turn(
        turn, session, "request" if channel == "foreground" else None, "Question", {"kind": channel}
    )
    history.append_recovery_event(session, stored_channel, 1, "turn_start", {"message_id": turn})
    history.append_recovery_event(session, stored_channel, 2, "delta", {"text": "Saved partial"})
    state = {"history": [{"role": "assistant", "content": "Saved partial"}]}
    with pytest.raises(TypeError):
        history.finish_recovery_turn(session, owner, expiry, state, stored_channel, 3, terminal, {"invalid": object()})
    record = history.load_recovery_session(session, owner)
    assert record["state"] == {}
    if channel == "background":
        assert record["background_status"] == "running"
    else:
        assert len(record["turns"]) == 1
    history.finish_recovery_turn(session, owner, expiry, state, stored_channel, 3, terminal, {"message_id": turn})
    history.append_recovery_event(session, stored_channel, 3, terminal, {"message_id": "duplicate"})
    record = history.load_recovery_session(session, owner)
    assert record["state"] == state
    if channel == "background":
        assert record["background_status"] == status
        events = record["background_events"]
    else:
        assert record["turns"] == []
        events = history.load_recovery_turn(session, "request")["events"]
        with history._connect() as connection:
            assert connection.execute("SELECT status FROM chat_recovery_turns").fetchone() == (status,)
    assert len(events) == 3
    assert events[-1]["data"] == {"message_id": turn}


def test_postgres_restored_background_keeps_entry_crossing_tail_boundary(postgres_history):
    from nurse_scheduling.ai.background import SessionEventBroker

    async def exercise():
        session, owner = str(uuid4()), str(uuid4())
        history = postgres_history
        history.save_recovery_session(session, owner, time.time() + 60, {})
        history.append_recovery_event(session, "background", 1, "turn_start", {"message_id": "background"})
        history.append_recovery_event(session, "background", 2, "delta", {"text": "First "})
        # Transient optimizer progress can leave large gaps in persisted stream cursors.
        history.append_recovery_event(session, "background", 1020, "delta", {"text": "last"})
        record = history.load_recovery_session(session, owner)
        assert record["background_events"][0]["data"] == {"text": "First last"}
        broker = SessionEventBroker(max_events_per_session=1)
        broker.load_snapshot = lambda sid: history.read("load_background_snapshot", sid)
        broker.on_publish = lambda sid, eid, kind, data: history.write(
            "append_recovery_event", sid, "background", eid, kind, data
        )
        broker.restore(session, record["background_events"])
        await broker.emit(session, "done", {"message_id": "background"})
        stream = broker.stream(session, 1019)
        snapshot = await anext(stream)
        await stream.aclose()
        assert (snapshot.id, snapshot.type) == (1021, "session_snapshot")
        assert snapshot.data["events"] == [
            {"type": "turn_start", "data": {"message_id": "background"}},
            {"type": "delta", "data": {"text": "First last"}},
            {"type": "done", "data": {"message_id": "background"}},
        ]

    asyncio.run(exercise())


def test_postgres_concurrent_channels_keep_all_text(postgres_history):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    session, owner, turn = str(uuid4()), str(uuid4()), str(uuid4())
    history = postgres_history
    history.save_recovery_session(session, owner, time.time() + 60, {})
    history.start_recovery_turn(turn, session, "request", "Question")
    barrier = Barrier(2)

    def publish(channel):
        barrier.wait(timeout=5)
        for cursor in range(1, 21):
            history.append_recovery_event(session, channel, cursor, "delta", {"text": str(cursor) + " "})

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(publish, [turn, "background"]))
    expected = "".join(str(cursor) + " " for cursor in range(1, 21))
    assert (
        "".join(event["data"]["text"] for event in history.load_recovery_turn(session, "request")["events"]) == expected
    )
    cursor, events = history.load_background_snapshot(session)
    assert cursor == 20
    assert events == [{"type": "delta", "data": {"text": expected}}]


def test_postgres_migrations_duplicates_and_reconnection(postgres_history):
    history = postgres_history
    turn, session, owner = str(uuid4()), str(uuid4()), str(uuid4())
    expiry = time.time() + 60
    history.save_recovery_session(session, owner, expiry, {}, "team-a")
    history.start_recovery_turn(turn, session, "request", "What's next?", {"model": "model", "attachment_count": 3})
    history.start_recovery_turn(turn, session, "request", "duplicate", {"model": "other"})
    history.append_recovery_event(session, turn, 1, "delta", {"text": "Answer"})
    history.finish_recovery_turn(session, owner, expiry, {}, turn, 2, "done", {}, {"usage": {"total_tokens": 3}})
    history.finish_recovery_turn(session, owner, expiry, {}, turn, 2, "stopped", {}, {"usage": {"total_tokens": 0}})
    restarted = ChatHistory("test")
    restarted.initialize()
    with restarted._connect() as connection:
        row = connection.execute(
            "SELECT question, model, status, usage, attachment_count, auth_credential_id, finished_at FROM chat_recovery_turns"
        ).fetchone()
        assert row[:6] == ("What's next?", "model", "completed", {"total_tokens": 3}, 3, "team-a")
        assert row[6] is not None
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (3,)
    assert restarted.load_recovery_turn(session, "request")["events"][0]["data"] == {"text": "Answer"}


def test_postgres_writes_survive_cancel_scope(postgres_history):
    import anyio

    turn, session, owner = str(uuid4()), str(uuid4()), str(uuid4())
    expiry = time.time() + 60
    postgres_history.save_recovery_session(session, owner, expiry, {})
    postgres_history.start_recovery_turn(turn, session, "request", "question")

    async def write_cancelled():
        with anyio.CancelScope() as scope:
            scope.cancel()
            assert await postgres_history.write(
                "finish_recovery_turn", session, owner, expiry, {}, turn, 1, "stopped", {}
            )

    anyio.run(write_cancelled)
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_recovery_turns").fetchone() == ("cancelled",)


def test_postgres_recovers_complete_message_and_history_after_backend_restart(postgres_history):
    settings = basic.make_settings(history_postgres_url="test")
    request = {"message": "Original question", "message_id": "stable-question"}
    answer = "FIRST" + "x" * 1200 + "LAST"
    first = basic.create_test_app(settings=settings, provider=basic.FakeProvider([["FIRST", *(["x"] * 1200), "LAST"]]))
    with basic.AuthenticatedTestClient(first) as client:
        session = basic.create_session(client)
        response = client.post(f"/sessions/{session}/messages", json=request)
        assert response.status_code == 200
        cookies = dict(client.cookies)
    provider = basic.FakeProvider([["This must never run"]])
    restarted = basic.create_test_app(settings=settings, provider=provider)
    with basic.AuthenticatedTestClient(restarted) as client:
        assert client.get(f"/sessions/{session}").status_code == 404
        client.cookies.update(cookies)
        assert client.get(f"/sessions/{session}").status_code == 200
        response = client.post(f"/sessions/{session}/messages", json=request)
        assert response.status_code == 200
        assert "turn_snapshot" in response.text
        assert answer in response.text
        assert provider.calls == []
        history = restarted.state.session_store._sessions[session].history
        assert [(item["role"], item["content"]) for item in history] == [
            ("user", "Original question"),
            ("assistant", answer),
        ]


def test_postgres_recovers_question_and_partial_output_from_interrupted_turn(postgres_history):
    import time

    session, turn, owner = str(uuid4()), str(uuid4()), str(uuid4())
    state = {
        "schedule_yaml": basic.schedule_yaml(),
        "history": [],
        "proposal_yaml": "",
        "proposal_diff": "",
        "dropped_history_messages": 0,
    }
    postgres_history.save_recovery_session(session, owner, time.time() + 60, state)
    postgres_history.start_recovery_turn(turn, session, "interrupted-question", "Keep working")
    postgres_history.append_recovery_event(session, turn, 1, "delta", {"text": "Saved partial output"})
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        client.cookies.set(basic.OWNER_COOKIE, owner)
        response = client.post(
            f"/sessions/{session}/messages", json={"message": "Keep working", "message_id": "interrupted-question"}
        )
        assert response.status_code == 200
        assert "Saved partial output" in response.text
        assert "service restarted" in response.text
        assert provider.calls == []
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, error_code FROM chat_recovery_turns").fetchone() == (
            "failed",
            "service_restart",
        )


def test_postgres_recovers_background_metadata_after_restart(postgres_history):
    session, owner, turn = str(uuid4()), str(uuid4()), str(uuid4())
    state = {
        "schedule_yaml": basic.schedule_yaml(),
        "history": [],
        "proposal_yaml": "",
        "proposal_diff": "",
        "dropped_history_messages": 0,
    }
    postgres_history.save_recovery_session(session, owner, time.time() + 60, state, "team-a")
    postgres_history.start_recovery_turn(turn, session, None, "Review result", {"kind": "background", "model": "model"})
    postgres_history.append_recovery_event(session, "background", 1, "turn_start", {"message_id": turn})
    postgres_history.append_recovery_event(session, "background", 2, "delta", {"text": "Saved background output"})
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        client.cookies.set(basic.OWNER_COOKIE, owner)
        assert client.get(f"/sessions/{session}").status_code == 200
        assert provider.calls == []
    with postgres_history._connect() as connection:
        assert connection.execute(
            "SELECT kind, auth_credential_id, model, status, error_code FROM chat_recovery_turns"
        ).fetchone() == ("background", "team-a", "model", "failed", "service_restart")
    _, events = postgres_history.load_background_snapshot(session)
    assert any(event["data"] == {"text": "Saved background output"} for event in events)


def test_postgres_background_replay_loads_complete_output_after_cache_eviction(postgres_history):
    from nurse_scheduling.ai.background import SessionEventBroker

    async def exercise():
        session, owner = str(uuid4()), str(uuid4())
        postgres_history.save_recovery_session(session, owner, time.time() + 60, {})
        broker = SessionEventBroker(max_events_per_session=2, max_snapshot_bytes=1)
        broker.on_publish = lambda sid, eid, kind, data: postgres_history.write(
            "append_recovery_event",
            sid,
            "background",
            eid,
            kind,
            data,
        )
        broker.load_snapshot = lambda sid: postgres_history.read("load_background_snapshot", sid)
        await broker.emit(session, "turn_start", {"message_id": "background"})
        for text in ("First ", "middle ", "last"):
            await broker.emit(session, "delta", {"text": text})
        await broker.emit(session, "done", {"message_id": "background"})
        assert session not in broker._snapshots
        stream = broker.stream(session, 0)
        snapshot = await anext(stream)
        await stream.aclose()
        assert snapshot.type == "session_snapshot"
        assert (
            "".join(event["data"]["text"] for event in snapshot.data["events"] if event["type"] == "delta")
            == "First middle last"
        )

    asyncio.run(exercise())


def test_postgres_foreground_replay_survives_completed_cache_eviction(postgres_history):
    from nurse_scheduling.ai.turns import TurnJournal

    async def exercise():
        session, owner, turn_id = str(uuid4()), str(uuid4()), str(uuid4())
        state = {"history": [{"role": "user", "content": "Question"}, {"role": "assistant", "content": "Saved answer"}]}
        expiry = time.time() + 60
        postgres_history.save_recovery_session(session, owner, expiry, {})
        journal = TurnJournal(postgres_history, max_cached_bytes=1)
        turn = await journal.start(session, turn_id, "request", "Question")
        await journal.publish(turn, "delta", {"text": "Saved answer"})
        await journal.finish(turn, "done", {"message_id": turn_id}, state=(owner, expiry, state))
        assert not journal.turns
        recovered = await journal.get(session, "request")
        assert recovered.terminal
        assert recovered.events[0] == {"type": "delta", "data": {"text": "Saved answer"}}
        assert not journal.turns
        with postgres_history._connect() as connection:
            assert connection.execute("SELECT state FROM chat_recovery_sessions").fetchone()[0] == state

    asyncio.run(exercise())


def test_postgres_recovery_enforces_owner_and_session_expiry(postgres_history):
    owner, other_owner = str(uuid4()), str(uuid4())
    expired, current = str(uuid4()), str(uuid4())
    for session, expiry in ((expired, time.time() - 1), (current, time.time() + 60)):
        postgres_history.save_recovery_session(session, owner, expiry, {})
        turn = str(uuid4())
        postgres_history.start_recovery_turn(turn, session, "question", "Original question")
        postgres_history.append_recovery_event(session, turn, 1, "delta", {"text": "Private answer"})
    assert postgres_history.load_recovery_session(current, other_owner) is None
    assert postgres_history.load_recovery_session(expired, owner) is None
    assert postgres_history.load_recovery_session(current, owner) is not None
    with postgres_history._connect() as connection:
        connection.execute(
            "UPDATE chat_recovery_sessions SET created_at = now() - interval '35 days' WHERE id = %s", (current,)
        )
        connection.execute(
            "UPDATE chat_recovery_turns SET started_at = now() - interval '35 days' WHERE session_id = %s", (current,)
        )
    # Retention follows renewed session expiry, rather than individual message age.
    postgres_history.prune()
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_recovery_sessions").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM chat_recovery_turns").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM chat_recovery_entries").fetchone() == (1,)


def test_postgres_stop_before_message_arrival_survives_restart(postgres_history):
    settings = basic.make_settings(history_postgres_url="test")
    first = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(first) as client:
        session = basic.create_session(client)
        cookies = dict(client.cookies)
        assert client.post(f"/sessions/{session}/stop", json={"message_id": "stopped-request"}).status_code == 202
    provider = basic.FakeProvider()
    restarted = basic.create_test_app(settings=settings, provider=provider)
    with basic.AuthenticatedTestClient(restarted) as client:
        client.cookies.update(cookies)
        result = client.post(
            f"/sessions/{session}/messages", json={"message": "Original question", "message_id": "stopped-request"}
        )
        assert basic.parse_sse(result.text, include_model_input=True)[-1][0] == "stopped"
        assert provider.calls == []
        assert restarted.state.session_store._sessions[session].history == []


@pytest.mark.parametrize("kind", ["foreground", "background"])
def test_postgres_shutdown_reports_interrupted_turn_as_restart(postgres_history, kind):
    started = asyncio.Event()

    class WaitingProvider:
        async def stream_events(self, messages, tools=None):
            yield TextDelta("Saved partial output")
            started.set()
            await asyncio.Event().wait()

    settings = basic.make_settings(history_postgres_url="test")

    async def exercise():
        app = basic.create_test_app(settings=settings, provider=WaitingProvider())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {basic.AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            if kind == "foreground":
                request = client.post(f"/sessions/{session_id}/messages", json={"message": "Q", "message_id": "m"})
            else:
                optimizer = app.state.session_optimizer
                request = optimizer._on_completion(session_id, "Optimizer finished", None)
            task = asyncio.create_task(request)
            if kind == "background":
                optimizer._tasks.add(task)
            await asyncio.wait_for(started.wait(), timeout=5)
            if kind == "foreground":
                # The browser disconnects while the server keeps working.
                task.cancel()
            await asyncio.sleep(0.1)
        await asyncio.gather(task, return_exceptions=True)
        return session_id, client.cookies.get(basic.OWNER_COOKIE)

    session_id, owner = asyncio.run(exercise())
    restarted = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(restarted) as client:
        client.cookies.set(basic.OWNER_COOKIE, owner)
        if kind == "foreground":
            response = client.post(f"/sessions/{session_id}/messages", json={"message": "Q", "message_id": "m"})
            assert "service restarted" in response.text and "Saved partial output" in response.text
        else:
            assert client.get(f"/sessions/{session_id}").status_code == 200
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, error_code FROM chat_recovery_turns").fetchone() == (
            "failed",
            "service_restart",
        )
