"""Durable AI chat history and session recovery in PostgreSQL."""

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

# This code is mostly AI generated.

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import anyio
import psycopg
from psycopg.types.json import Jsonb

from .provider import TokenUsage
from .transcript import AgentMessage, ProposalDecision, ProposalDecisionEntry, UserMessage, entry_record

logger = logging.getLogger("nurse_scheduling.ai.history")
RunStatus = Literal["completed", "failed", "cancelled", "stale"]
RunKind = Literal["foreground", "background"]
# The owner token, expiry in epoch seconds, and JSON state that restore needs.
SessionState = tuple[str, float, dict[str, Any]]
# One stored stream event: first and last event ID, run ID, type, and data.
EventRow = tuple[int, int, str | None, str, dict[str, Any]]
RECOVERY_UNAVAILABLE = "AI message recovery is temporarily unavailable."


def _owner_hash(owner: str) -> str:
    """Store only a digest, so the database never holds a usable owner cookie."""
    return hashlib.sha256(owner.encode()).hexdigest()


def _jsonb(value: Any) -> Jsonb:
    """Replace NUL characters, which PostgreSQL jsonb rejects, so a retried write can succeed.

    Tool output can contain them, for example when a command prints a binary upload.
    """

    def storable(item: Any) -> Any:
        if isinstance(item, str):
            return item.replace("\x00", "\ufffd")
        if isinstance(item, dict):
            return {storable(key): storable(child) for key, child in item.items()}
        if isinstance(item, list | tuple):
            return [storable(child) for child in item]
        return item

    return Jsonb(storable(value))


class ChatHistory:
    """Use bounded transactions off the event loop, shielded during disconnects."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self):
        return psycopg.connect(
            self._database_url,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=5000",
        )

    def initialize(self) -> None:
        """Apply numbered migrations transactionally, serialized across processes."""
        with self._connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(782341926)")
            connection.execute("CREATE TABLE IF NOT EXISTS ai_history_migrations (version text PRIMARY KEY)")
            for migration in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
                applied = connection.execute(
                    "SELECT 1 FROM ai_history_migrations WHERE version = %s", (migration.name,)
                ).fetchone()
                if not applied:
                    connection.execute(migration.read_text(encoding="utf-8"))
                    connection.execute("INSERT INTO ai_history_migrations (version) VALUES (%s)", (migration.name,))
        self.prune()

    def prune(self) -> None:
        """Delete expired sessions with their runs, entries, events, and Stop requests."""
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_sessions WHERE expires_at < now()")

    @staticmethod
    def _save_state(connection, session_id: str, state: SessionState, credential_id: str | None = None) -> None:
        owner, expires_at, data = state
        connection.execute(
            "INSERT INTO chat_sessions (id, owner_hash, expires_at, state, auth_credential_id) "
            "VALUES (%s, %s, to_timestamp(%s), %s, %s) ON CONFLICT (id) DO UPDATE SET "
            "expires_at = EXCLUDED.expires_at, state = EXCLUDED.state",
            (session_id, _owner_hash(owner), expires_at, _jsonb(data), credential_id),
        )

    def save_session(self, session_id: str, state: SessionState, credential_id: str | None = None) -> None:
        """Keep session ownership, expiry, schedule, proposal, and conversation context."""
        with self._connect() as connection:
            self._save_state(connection, session_id, state, credential_id)

    def start_run(
        self,
        run_id: str,
        session_id: str,
        state: SessionState,
        prompt: str,
        *,
        model: str,
        attachment_count: int,
        kind: RunKind = "foreground",
        message_id: str | None = None,
        credential_id: str | None = None,
    ) -> None:
        """Atomically save the session state, a uniquely identified run, and its prompt entry.

        The prompt is written before model work, so it survives a process that dies mid-run.
        """
        with self._connect() as connection:
            self._save_state(connection, session_id, state)
            inserted = connection.execute(
                "INSERT INTO chat_runs (id, session_id, model, attachment_count, kind, message_id, auth_credential_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, "
                "coalesce(%s, (SELECT auth_credential_id FROM chat_sessions WHERE id = %s))) "
                "ON CONFLICT (id) DO NOTHING RETURNING id",
                (run_id, session_id, model, attachment_count, kind, message_id, credential_id, session_id),
            ).fetchone()
            if inserted is not None:
                _insert_entries(connection, run_id, 0, [UserMessage(prompt)])

    def finish_run(
        self,
        run_id: str,
        status: RunStatus,
        error_code: str | None,
        usage: TokenUsage | None,
        entries: Sequence[AgentMessage] = (),
        session_id: str | None = None,
        state: SessionState | None = None,
    ) -> None:
        """Commit the run outcome with the resulting session state, keeping the first terminal result.

        `entries` continue the prompt written by `start_run` in run order.
        """
        with self._connect() as connection:
            if session_id is not None and state is not None:
                self._save_state(connection, session_id, state)
            finished = connection.execute(
                "UPDATE chat_runs SET status = %s, error_code = %s, usage = %s, finished_at = now() "
                "WHERE id = %s AND status = 'running' RETURNING id",
                (status, error_code, Jsonb(asdict(usage)) if usage else None, run_id),
            ).fetchone()
            if finished is not None:
                _insert_entries(connection, run_id, 1, entries)

    def record_decision(
        self, session_id: str, state: SessionState, run_id: str | None, decision: ProposalDecision
    ) -> None:
        """Save the decided session state and append the decision to the run that proposed it."""
        with self._connect() as connection:
            self._save_state(connection, session_id, state)
            if run_id is None:
                return
            (next_seq,) = connection.execute(
                "SELECT COALESCE(max(seq) + 1, 0) FROM chat_run_entries WHERE run_id = %s", (run_id,)
            ).fetchone()
            _insert_entries(connection, run_id, next_seq, [ProposalDecisionEntry(decision)])

    def append_events(self, session_id: str, rows: Sequence[EventRow]) -> None:
        """Store replayable events in publication order. A retried batch keeps the first copy."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chat_session_events (session_id, event_id, last_event_id, run_id, type, data) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                [(session_id, first, last, run_id, kind, _jsonb(data)) for first, last, run_id, kind, data in rows],
            )

    def stop_message(self, session_id: str, message_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_run_stops (session_id, message_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (session_id, message_id),
            )

    def message_stopped(self, session_id: str, message_id: str) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM chat_run_stops WHERE session_id = %s AND message_id = %s",
                    (session_id, message_id),
                ).fetchone()
                is not None
            )

    def find_message(self, session_id: str, message_id: str) -> tuple[str, str] | None:
        """Return the run ID and prompt of an accepted client message."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT r.id, e.payload->>'text' FROM chat_runs r "
                "JOIN chat_run_entries e ON e.run_id = r.id AND e.seq = 0 "
                "WHERE r.session_id = %s AND r.message_id = %s",
                (session_id, message_id),
            ).fetchone()
        return None if row is None else (str(row[0]), row[1])

    def load_session(self, session_id: str, owner: str) -> dict[str, Any] | None:
        """Load an unexpired owned session and the runs whose terminal event was not stored."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, extract(epoch FROM expires_at) FROM chat_sessions "
                "WHERE id = %s AND owner_hash = %s AND expires_at > now()",
                (session_id, _owner_hash(owner)),
            ).fetchone()
            if row is None:
                return None
            (last_event_id,) = connection.execute(
                "SELECT coalesce(max(last_event_id), 0) FROM chat_session_events WHERE session_id = %s",
                (session_id,),
            ).fetchone()
            unfinished = connection.execute(
                "SELECT r.id, r.kind, r.status FROM chat_runs r WHERE r.session_id = %s AND NOT EXISTS ("
                "SELECT 1 FROM chat_session_events e WHERE e.session_id = r.session_id AND e.run_id = r.id "
                "AND e.type IN ('done', 'stopped', 'stale', 'error')) ORDER BY r.sequence",
                (session_id,),
            ).fetchall()
        return {
            "state": row[0],
            "expires_at": float(row[1]),
            "last_event_id": int(last_event_id),
            "unfinished_runs": [
                {"id": str(run_id), "kind": kind, "status": status} for run_id, kind, status in unfinished
            ],
        }

    def load_events(self, session_id: str, after_id: int) -> list[EventRow]:
        """Load events after a cursor, with every stored event of the runs they belong to.

        A combined text row can start before the cursor. Replacing its whole run avoids
        repeating the part the browser already shows.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, last_event_id, run_id, type, data FROM chat_session_events "
                "WHERE session_id = %s AND (last_event_id > %s OR run_id IN ("
                "SELECT run_id FROM chat_session_events WHERE session_id = %s AND last_event_id > %s "
                "AND run_id IS NOT NULL)) ORDER BY event_id",
                (session_id, after_id, session_id, after_id),
            ).fetchall()
        return [
            (first, last, None if run_id is None else str(run_id), kind, data)
            for first, last, run_id, kind, data in rows
        ]

    async def read(self, operation: str, *args):
        """Run a lookup. A failure becomes a RuntimeError that callers map to HTTP 503."""
        try:
            with anyio.CancelScope(shield=True):
                return await anyio.to_thread.run_sync(getattr(self, operation), *args)
        except (psycopg.Error, OSError):
            logger.error("AI history %s failed", operation)
            raise RuntimeError(RECOVERY_UNAVAILABLE) from None

    async def write(self, operation: str, *args, **kwargs) -> bool:
        """Report failures without leaking connection strings or chat text to logs."""
        try:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(lambda: getattr(self, operation)(*args, **kwargs))
            return True
        except (psycopg.Error, OSError):
            logger.error("AI history %s failed", operation)
            return False

    async def maintain(self) -> None:
        """Apply retention hourly even when there are no chat requests."""
        while True:
            await asyncio.sleep(3600)
            await self.write("prune")


def _insert_entries(connection, run_id: str, first_seq: int, entries: Sequence[AgentMessage]) -> None:
    rows = [(run_id, seq, *entry_record(entry)) for seq, entry in enumerate(entries, first_seq)]
    if rows:
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chat_run_entries (run_id, seq, type, payload) VALUES (%s, %s, %s, %s)",
                [(run_id, seq, kind, _jsonb(payload)) for run_id, seq, kind, payload in rows],
            )


async def stop_maintenance(task: asyncio.Task) -> None:
    """Join the retention worker during application shutdown."""
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
