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
import json
import os
from dataclasses import asdict
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.history import ChatHistory
from nurse_scheduling.ai.provider import ProviderError, ReasoningDelta, TextDelta, TokenUsage
from nurse_scheduling.ai.transcript import (
    AssistantMessage,
    ProposalDecisionEntry,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

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


def test_postgres_stream_records_ordered_runs_and_partial_failure(postgres_history):
    provider = basic.FakeProvider([["Answer"], ["Partial", ProviderError("private detail")]])
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        for question in ["First", "Second"]:
            client.post(f"/sessions/{session_id}/messages", json={"message": question})
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, error_code FROM chat_runs ORDER BY sequence").fetchall() == [
            ("completed", None),
            ("failed", "provider_error"),
        ]
        assert run_entries(connection) == [
            record(UserMessage("First")),
            record(AssistantMessage("Answer")),
            record(UserMessage("Second")),
            record(AssistantMessage("Partial", "error")),
        ]


@pytest.fixture
def recorded_history(monkeypatch):
    records = {"starts": [], "finishes": []}
    monkeypatch.setattr(ChatHistory, "initialize", lambda _self: None)
    monkeypatch.setattr(ChatHistory, "start_run", lambda _self, *args: records["starts"].append(args))
    monkeypatch.setattr(ChatHistory, "finish_run", lambda _self, *args: records["finishes"].append(args))
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

    monkeypatch.setattr(ChatHistory, "start_run", unavailable)
    provider = basic.FakeProvider()
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
        assert response.status_code == 503
        assert provider.calls == []
        monkeypatch.setattr(ChatHistory, "start_run", lambda *_args: None)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})
        assert basic.parse_sse(response.text)[-1][0] == "done"


def test_final_write_failure_preserves_successful_conversation(recorded_history, monkeypatch, caplog):
    def unavailable(*_args):
        raise psycopg.OperationalError("secret-database-url")

    monkeypatch.setattr(ChatHistory, "finish_run", unavailable)
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
    assert basic.parse_sse(response.text)[-1][1]["history_saved"] is False
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


def record(entry) -> tuple[str, dict]:
    """Return the stored type and payload expected for one agent message."""
    kind = {
        UserMessage: "user",
        AssistantMessage: "assistant",
        ToolResultMessage: "tool_result",
        ProposalDecisionEntry: "proposal_decision",
    }[type(entry)]
    # JSON stores tuples as arrays.
    return kind, json.loads(json.dumps(asdict(entry)))


def run_entries(connection) -> list[tuple[str, dict]]:
    """Return every entry in run and entry order."""
    return connection.execute(
        "SELECT e.type, e.payload FROM chat_run_entries e "
        "JOIN chat_runs r ON r.id = e.run_id ORDER BY r.sequence, e.seq"
    ).fetchall()


@pytest.fixture
def postgres_history(monkeypatch):
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
        history = ChatHistory(database_url)
        history.initialize()
        yield history
    finally:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_duplicates_and_reconnection(postgres_history):
    history = postgres_history
    run, session = str(uuid4()), str(uuid4())
    history.start_run(run, session, "team-a", "What's next?", "model", 3)
    history.start_run(run, session, "team-a", "duplicate", "model", 3)
    call = ToolCall("call-1", "read", '{"path":"schedule.yaml"}')
    entries = [
        AssistantMessage("Checking.", "tool_use", "Look first.", (call,)),
        ToolResultMessage("call-1", "read", "people: []", True),
        UserMessage("Only nights."),
        AssistantMessage("Answer"),
    ]
    history.finish_run(run, "completed", None, TokenUsage(1, 2, 3), entries)
    history.finish_run(run, "cancelled", None, None, [AssistantMessage("Overwrite", "aborted")])
    history.record_decision(run, "approved")
    restarted = ChatHistory("test")
    restarted.initialize()
    with restarted._connect() as connection:
        row = connection.execute("SELECT status, usage, finished_at, attachment_count FROM chat_runs").fetchone()
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
        assert run_entries(connection) == [
            record(UserMessage("What's next?")),
            *map(record, entries),
            record(ProposalDecisionEntry("approved")),
        ]
        credential_id = connection.execute("SELECT auth_credential_id FROM chat_sessions").fetchone()
        assert credential_id == ("team-a",)
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (1,)


def test_postgres_retention_preserves_recent_runs(postgres_history):
    history = postgres_history
    session = str(uuid4())
    old, recent = str(uuid4()), str(uuid4())
    history.start_run(old, session, None, "old", "model", 0)
    history.start_run(recent, session, None, "recent", "model", 0)
    with history._connect() as connection:
        connection.execute("UPDATE chat_runs SET started_at = now() - interval '31 days' WHERE id = %s", (old,))
        connection.execute("UPDATE chat_sessions SET created_at = now() - interval '31 days'")
    history.prune()
    with history._connect() as connection:
        assert run_entries(connection) == [record(UserMessage("recent"))]
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (1,)
        connection.execute("UPDATE chat_runs SET started_at = now() - interval '31 days'")
    history.prune()
    with history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM chat_run_entries").fetchone() == (0,)


def test_postgres_writes_survive_cancel_scope(postgres_history):
    import anyio

    run, session = str(uuid4()), str(uuid4())
    postgres_history.start_run(run, session, None, "question", "model", 0)

    async def cancel_and_save():
        with anyio.CancelScope() as scope:
            scope.cancel()
            assert await postgres_history.write(
                "finish_run", run, "cancelled", None, None, [AssistantMessage("partial", "aborted")]
            )

    asyncio.run(cancel_and_save())
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status FROM chat_runs").fetchone() == ("cancelled",)
        assert run_entries(connection)[-1] == record(AssistantMessage("partial", "aborted"))
