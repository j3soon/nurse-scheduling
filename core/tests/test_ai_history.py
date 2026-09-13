"""AI audit logging lifecycle and PostgreSQL persistence checks."""

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
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

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
        assert connection.execute(
            "SELECT user_message, assistant_message, status, error_code FROM chat_turns ORDER BY sequence"
        ).fetchall() == [("First", "Answer", "completed", None), ("Second", "Partial", "failed", "provider_error")]


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
    assert start[3:] == ("Question", "test-model", 0, 0)
    assert finish == (
        start[0],
        "Partial answer",
        "failed" if failed else "completed",
        "provider_error" if failed else None,
        TokenUsage(3, 4, 7),
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


def test_postgres_migrations_duplicates_and_reconnection(postgres_history):
    history = postgres_history
    turn, session = str(uuid4()), str(uuid4())
    history.start_turn(turn, session, "team-a", "What's next?", "model", 1, 2)
    history.start_turn(turn, session, "team-a", "duplicate", "model", 1, 2)
    history.finish_turn(turn, "Answer", "completed", None, TokenUsage(1, 2, 3))
    history.finish_turn(turn, "Overwrite", "cancelled", None, None)
    restarted = ChatHistory("test")
    restarted.initialize()
    with restarted._connect() as connection:
        row = connection.execute(
            "SELECT user_message, assistant_message, status, usage, finished_at FROM chat_turns"
        ).fetchone()
        assert row[:4] == (
            "What's next?",
            "Answer",
            "completed",
            {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "cached_prompt_tokens": 0,
                "reasoning_tokens": 0,
            },
        )
        assert row[4] is not None
        credential_id = connection.execute("SELECT auth_credential_id FROM chat_sessions").fetchone()
        assert credential_id == ("team-a",)
        assert connection.execute("SELECT count(*) FROM ai_history_migrations").fetchone() == (1,)


def test_postgres_retention_preserves_recent_turns(postgres_history):
    history = postgres_history
    session = str(uuid4())
    old, recent = str(uuid4()), str(uuid4())
    history.start_turn(old, session, None, "old", "model", 0, 0)
    history.start_turn(recent, session, None, "recent", "model", 0, 0)
    with history._connect() as connection:
        connection.execute("UPDATE chat_turns SET started_at = now() - interval '31 days' WHERE id = %s", (old,))
        connection.execute("UPDATE chat_sessions SET created_at = now() - interval '31 days'")
    history.prune()
    with history._connect() as connection:
        assert connection.execute("SELECT user_message FROM chat_turns").fetchall() == [("recent",)]
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (1,)
        connection.execute("UPDATE chat_turns SET started_at = now() - interval '31 days'")
    history.prune()
    with history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_sessions").fetchone() == (0,)


def test_postgres_writes_survive_cancel_scope(postgres_history):
    import anyio

    turn, session = str(uuid4()), str(uuid4())
    postgres_history.start_turn(turn, session, None, "question", "model", 0, 0)

    async def cancel_and_save():
        with anyio.CancelScope() as scope:
            scope.cancel()
            assert await postgres_history.write("finish_turn", turn, "partial", "cancelled", None, None)

    asyncio.run(cancel_and_save())
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT status, assistant_message FROM chat_turns").fetchone() == (
            "cancelled",
            "partial",
        )
