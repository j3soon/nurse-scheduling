"""AI chat history lifecycle and PostgreSQL persistence checks."""

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
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from nurse_scheduling.ai import history as ai_history
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.history import ChatHistory
from nurse_scheduling.ai.provider import ProviderError, ReasoningDelta, TextDelta, TokenUsage
from nurse_scheduling.ai.transcript import AssistantMessage, ToolCall, ToolResultMessage, UserMessage

from . import test_ai_basic as basic


def test_history_environment_settings(monkeypatch):
    for name, value in {
        "AI_PROVIDER_API_KEY": "test-token",
        "AI_PROVIDER_BASE_URL": "https://provider.example/v1",
        "AI_SANDBOX_BACKEND": "e2b",
        "E2B_API_KEY": "test-e2b-key",
        "AI_HISTORY_POSTGRES_URL": " postgresql:///history ",
        "AI_HISTORY_RETENTION_DAYS": "7",
    }.items():
        monkeypatch.setenv(name, value)
    settings = AiSettings.from_env()
    assert settings.history_postgres_url == "postgresql:///history"
    assert settings.history_retention_days == 7
    monkeypatch.setenv("AI_HISTORY_RETENTION_DAYS", "0")
    with pytest.raises(ValueError, match="AI_HISTORY_RETENTION_DAYS"):
        AiSettings.from_env()


def test_postgres_stream_records_ordered_turns_and_partial_failure(postgres_history):
    provider = basic.FakeProvider([["Answer"], ["Partial", ProviderError("private detail")]])
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        for question in ["First", "Second"]:
            client.post(f"/sessions/{session_id}/messages", json={"message": question})
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, error_code FROM chat_turns ORDER BY sequence").fetchall() == [
            ("completed", None),
            ("failed", "provider_error"),
        ]
        assert turn_entries(connection) == [
            ("user", "First", None, None),
            ("assistant", "Answer", "stop", None),
            ("user", "Second", None, None),
            ("assistant", "Partial", "error", None),
        ]


@pytest.fixture
def recorded_history(monkeypatch):
    records = {"starts": [], "finishes": []}
    monkeypatch.setattr(ChatHistory, "initialize", lambda _self: None)
    monkeypatch.setattr(ChatHistory, "start_turn", lambda _self, *args: records["starts"].append(args))
    monkeypatch.setattr(ChatHistory, "finish_turn", lambda _self, *args: records["finishes"].append(args))
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
    assert start[1] == session_id
    assert start[3:] == ("Question", "test-model", 0)
    assert finish == (
        start[0],
        "failed" if failed else "completed",
        "provider_error" if failed else None,
        TokenUsage(3, 4, 7),
        [AssistantMessage("Partial answer", "error" if failed else "stop")],
    )
    if not failed:
        assert basic.parse_sse(response.text)[-1] == ("done", {"message_id": start[0], "history_saved": True})
    assert "private provider credential" not in repr(recorded_history)


def test_database_unavailable_releases_session_before_provider_call(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "start_turn", unavailable)
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
        assert response.status_code == 503
        assert provider.calls == []
        monkeypatch.setattr(ChatHistory, "start_turn", lambda *_args: None)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})
        assert basic.parse_sse(response.text)[-1][0] == "done"


def test_final_write_failure_preserves_successful_conversation(recorded_history, monkeypatch, caplog):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "finish_turn", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
    assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
    assert "AI history finish_turn failed" in caplog.text
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
    (finish,) = recorded_history["finishes"]
    assert start[3] == "Is Monday covered?"
    assert finish[4] == [
        AssistantMessage("Monday is covered."),
        UserMessage("And Tuesday?"),
        AssistantMessage("Tuesday is covered."),
    ]


def test_history_records_the_prompt_the_model_saw_with_attachment_names(recorded_history):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"),
        provider=basic.FakeProvider([["Seen."]]),
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        client.post(
            f"/sessions/{session_id}/messages",
            data={"message": "Read this."},
            files={"files": ("ward.xlsx", b"bytes", "application/octet-stream")},
        )
        prompt = app.state.session_store._sessions[session_id].transcript[0]

    (start,) = recorded_history["starts"]
    assert start[3:] == (prompt.text, "test-model", 1)
    assert "ward.xlsx" in prompt.text


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

    (finish,) = recorded_history["finishes"]
    (call,) = basic.rename_call()[0].calls
    tool_use, tool_result, answer = finish[4]
    assert tool_use == AssistantMessage("Checking. ", "tool_use", "Find P1. ", (call,))
    assert (tool_result.tool_call_id, tool_result.tool_name, tool_result.ok) == (call.id, call.name, True)
    assert "passed trusted server-side validation" in tool_result.text
    assert answer == AssistantMessage("Renamed P1.")
    assert retained == [UserMessage("Rename P1."), AssistantMessage("Checking. ", "tool_use"), answer]


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_proposal_decisions_join_the_run_that_proposed_them(recorded_history, monkeypatch, decision):
    decisions = []
    monkeypatch.setattr(ChatHistory, "record_decision", lambda _self, *args: decisions.append(args))
    provider = basic.ScriptedToolProvider(basic.rename_call(), [basic.TextDelta("Renamed P1.")])
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test", max_schedule_bytes=basic.SCHEDULE_BYTE_LIMIT),
        provider=provider,
        sandbox_factory=basic.rename_factory(),
    )
    with basic.AuthenticatedTestClient(app) as client:
        schedule = basic.schedule_yaml()
        session_id = basic.create_session(client, schedule)
        client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})
        if decision == "approved":
            revision = hashlib.sha256(schedule.encode("utf-8")).hexdigest()
            response = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
        else:
            response = client.post(f"/sessions/{session_id}/proposal/reject")
        assert response.is_success
        # Without a pending proposal there is nothing to decide or record.
        client.post(f"/sessions/{session_id}/proposal/reject")

    (start,) = recorded_history["starts"]
    assert decisions == [(start[0], decision)]


def test_database_unavailable_prevents_startup(recorded_history, monkeypatch):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret")

    monkeypatch.setattr(ChatHistory, "initialize", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with pytest.raises(RuntimeError, match="database initialization failed"), basic.AuthenticatedTestClient(app):
        pass


def turn_entries(connection) -> list[tuple]:
    """Return every entry in turn and entry order."""
    return connection.execute(
        "SELECT e.type, e.text, e.stop_reason, e.decision FROM chat_turn_entries e "
        "JOIN chat_turns t ON t.id = e.turn_id ORDER BY t.sequence, e.seq"
    ).fetchall()


@pytest.fixture
def postgres_schema(monkeypatch):
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
def postgres_history(postgres_schema):
    postgres_schema.initialize()
    return postgres_schema


def test_postgres_migrations_duplicates_and_reconnection(postgres_history):
    history = postgres_history
    turn, session = str(uuid4()), str(uuid4())
    history.start_turn(turn, session, "team-a", "What's next?", "model", 3)
    history.start_turn(turn, session, "team-a", "duplicate", "model", 3)
    call = ToolCall("call-1", "read", '{"path":"schedule.yaml"}')
    entries = [
        AssistantMessage("Checking.", "tool_use", "Look first.", (call,)),
        ToolResultMessage("call-1", "read", "people: []", True),
        UserMessage("Only nights."),
        AssistantMessage("Answer"),
    ]
    history.finish_turn(turn, "completed", None, TokenUsage(1, 2, 3), entries)
    history.finish_turn(turn, "cancelled", None, None, [AssistantMessage("Overwrite", "aborted")])
    history.record_decision(turn, "approved")
    restarted = ChatHistory("test")
    restarted.initialize()
    with restarted._connect() as connection:
        row = connection.execute("SELECT status, usage, finished_at, attachment_count FROM chat_turns").fetchone()
        assert row[:2] == (
            "completed",
            {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "cached_prompt_tokens": 0,
                "reasoning_tokens": 0,
            },
        )
        assert row[2] is not None
        assert row[3] == 3
        assert turn_entries(connection) == [
            ("user", "What's next?", None, None),
            ("assistant", "Checking.", "tool_use", None),
            ("tool_result", "people: []", None, None),
            ("user", "Only nights.", None, None),
            ("assistant", "Answer", "stop", None),
            ("proposal_decision", None, None, "approved"),
        ]
        assert connection.execute(
            "SELECT reasoning, tool_calls FROM chat_turn_entries WHERE type = 'assistant' ORDER BY seq LIMIT 1"
        ).fetchone() == ("Look first.", [{"id": "call-1", "name": "read", "arguments": '{"path":"schedule.yaml"}'}])
        assert connection.execute(
            "SELECT tool_call_id, tool_name, ok FROM chat_turn_entries WHERE type = 'tool_result'"
        ).fetchone() == ("call-1", "read", True)
        credential_id = connection.execute("SELECT auth_credential_id FROM chat_sessions").fetchone()
        assert credential_id == ("team-a",)
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (3,)


def test_postgres_retention_preserves_recent_turns(postgres_history):
    history = postgres_history
    session = str(uuid4())
    old, recent = str(uuid4()), str(uuid4())
    history.start_turn(old, session, None, "old", "model", 0)
    history.start_turn(recent, session, None, "recent", "model", 0)
    with history._connect() as connection:
        connection.execute("UPDATE chat_turns SET started_at = now() - interval '31 days' WHERE id = %s", (old,))
        connection.execute("UPDATE chat_sessions SET created_at = now() - interval '31 days'")
    history.prune()
    with history._connect() as connection:
        assert turn_entries(connection) == [("user", "recent", None, None)]
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (1,)
        connection.execute("UPDATE chat_turns SET started_at = now() - interval '31 days'")
    history.prune()
    with history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM chat_turn_entries").fetchone() == (0,)


def test_postgres_writes_survive_cancel_scope(postgres_history):
    import anyio

    turn, session = str(uuid4()), str(uuid4())
    postgres_history.start_turn(turn, session, None, "question", "model", 0)

    async def cancel_and_save():
        with anyio.CancelScope() as scope:
            scope.cancel()
            assert await postgres_history.write(
                "finish_turn", turn, "cancelled", None, None, [AssistantMessage("partial", "aborted")]
            )

    asyncio.run(cancel_and_save())
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_turns").fetchone() == ("cancelled",)
        assert turn_entries(connection)[-1] == ("assistant", "partial", "aborted", None)


def test_postgres_migration_moves_legacy_turn_text_into_entries(postgres_schema):
    migrations = sorted(Path(ai_history.__file__).with_name("migrations").glob("*.sql"))
    completed, cancelled, running = str(uuid4()), str(uuid4()), str(uuid4())
    session = str(uuid4())
    with postgres_schema._connect() as connection:
        connection.execute("CREATE TABLE ai_history_migrations (version text PRIMARY KEY)")
        for migration in migrations[:2]:
            connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO ai_history_migrations (version) VALUES (%s)", (migration.name,))
        connection.execute("INSERT INTO chat_sessions (id) VALUES (%s)", (session,))
        for turn, user_message, assistant_message, status in [
            (completed, "Q1", "A1", "completed"),
            (cancelled, "Q2", "partial", "cancelled"),
            (running, "Q3", "", "running"),
        ]:
            connection.execute(
                "INSERT INTO chat_turns (id, session_id, user_message, assistant_message, model, status) "
                "VALUES (%s, %s, %s, %s, 'model', %s)",
                (turn, session, user_message, assistant_message, status),
            )

    postgres_schema.initialize()

    with postgres_schema._connect() as connection:
        assert turn_entries(connection) == [
            ("user", "Q1", None, None),
            ("assistant", "A1", "stop", None),
            ("user", "Q2", None, None),
            ("assistant", "partial", "aborted", None),
            ("user", "Q3", None, None),
        ]
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'chat_turns' AND table_schema = current_schema()"
            )
        }
        assert not columns & {"user_message", "assistant_message", "transcript"}
