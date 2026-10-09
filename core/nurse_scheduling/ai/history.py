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
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Literal

import anyio
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

from ..sentry import report_outage_recovery
from ..server.retry import RepeatedFailure
from .provider import TokenUsage
from .transcript import AgentMessage, AssistantMessage, UserMessage, entry_from_record, entry_record

logger = logging.getLogger("nurse_scheduling.ai.history")
RunStatus = Literal["completed", "failed", "cancelled", "stale"]
RunKind = Literal["foreground", "background"]
# The owner token, expiry in epoch seconds, and JSON state that restore needs.
SessionState = tuple[str, float, dict[str, Any]]
# One stored stream event: first and last event ID, run ID, type, and data.
EventRow = tuple[int, int, str | None, str, dict[str, Any]]
# One conversation entry in session order: sequence number, run ID, and entry.
EntryRow = tuple[int, str | None, AgentMessage]
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
        options = conninfo_to_dict(self._database_url).get("options", "")
        return psycopg.connect(
            self._database_url,
            connect_timeout=5,
            options=f"{options} -c statement_timeout=5000 -c lock_timeout=5000".strip(),
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
                    if migration.name == "004_unified_session_recovery.sql":
                        _migrate_legacy_transcripts(connection)
                    connection.execute("INSERT INTO ai_history_migrations (version) VALUES (%s)", (migration.name,))
        self.prune()

    def prune(self) -> None:
        """Delete expired sessions with their runs, entries, events, and Stop requests."""
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_sessions WHERE expires_at < now()")

    @staticmethod
    def _save_state(
        connection,
        session_id: str,
        state: SessionState,
        entries: Sequence[EntryRow],
        credential_id: str | None = None,
    ) -> None:
        """Save the state with the entries it counts, so a restore never skips an unsaved entry."""
        owner, expires_at, data = state
        connection.execute(
            "INSERT INTO chat_sessions (id, owner_hash, expires_at, state, auth_credential_id) "
            "VALUES (%s, %s, to_timestamp(%s), %s, %s) ON CONFLICT (id) DO UPDATE SET "
            "expires_at = EXCLUDED.expires_at, state = EXCLUDED.state",
            (session_id, _owner_hash(owner), expires_at, _jsonb(data), credential_id),
        )
        _insert_entries(connection, session_id, entries)

    def save_session(
        self,
        session_id: str,
        state: SessionState,
        credential_id: str | None = None,
        *,
        entries: Sequence[EntryRow] = (),
    ) -> None:
        """Keep session ownership, expiry, schedule, proposal, and new conversation entries."""
        with self._connect() as connection:
            self._save_state(connection, session_id, state, entries, credential_id)

    def append_entries(self, session_id: str, entries: Sequence[EntryRow]) -> None:
        """Save entries as they end, as Pi saves each message on `message_end`."""
        with self._connect() as connection:
            _insert_entries(connection, session_id, entries)

    def start_run(
        self,
        run_id: str,
        session_id: str,
        state: SessionState,
        prompt: str,
        prompt_seq: int,
        *,
        model: str,
        attachment_count: int,
        kind: RunKind = "foreground",
        message_id: str | None = None,
        credential_id: str | None = None,
        entries: Sequence[EntryRow] = (),
    ) -> None:
        """Atomically save the session state, a uniquely identified run, and its prompt entry.

        The prompt is written before model work, so it survives a process that dies mid-run.
        """
        with self._connect() as connection:
            self._save_state(connection, session_id, state, entries)
            inserted = connection.execute(
                "INSERT INTO chat_runs (id, session_id, model, attachment_count, kind, message_id, auth_credential_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, "
                "coalesce(%s, (SELECT auth_credential_id FROM chat_sessions WHERE id = %s))) "
                "ON CONFLICT (id) DO NOTHING RETURNING id",
                (run_id, session_id, model, attachment_count, kind, message_id, credential_id, session_id),
            ).fetchone()
            if inserted is not None:
                _insert_entries(connection, session_id, [(prompt_seq, run_id, UserMessage(prompt))])

    def finish_run(
        self,
        run_id: str,
        status: RunStatus,
        error_code: str | None,
        usage: TokenUsage | None,
        committed: bool = False,
        *,
        session_id: str,
        state: SessionState,
        entries: Sequence[EntryRow] = (),
    ) -> None:
        """Commit the run outcome with the resulting session state, keeping the first terminal result.

        `committed` records whether the run's messages joined the session conversation.
        """
        with self._connect() as connection:
            self._save_state(connection, session_id, state, entries)
            connection.execute(
                "UPDATE chat_runs SET status = %s, error_code = %s, usage = %s, committed = %s, finished_at = now() "
                "WHERE id = %s AND status = 'running'",
                (status, error_code, Jsonb(asdict(usage)) if usage else None, committed, run_id),
            )

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
                "JOIN chat_session_entries e ON e.run_id = r.id AND e.type = 'user' "
                "WHERE r.session_id = %s AND r.message_id = %s ORDER BY e.seq LIMIT 1",
                (session_id, message_id),
            ).fetchone()
        return None if row is None else (str(row[0]), row[1])

    def recover_run(self, session_id: str, run_id: str) -> None:
        """Retain safe context for an accepted run that a dead process left unfinished."""
        with self._connect() as connection:
            connection.execute("SELECT id FROM chat_sessions WHERE id = %s FOR UPDATE", (session_id,))
            run = connection.execute(
                "SELECT status, message_id FROM chat_runs WHERE id = %s AND session_id = %s FOR UPDATE",
                (run_id, session_id),
            ).fetchone()
            if run is None or run[0] != "running":
                return
            stopped_before_work = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM chat_run_stops WHERE session_id = %s AND message_id = %s) "
                "AND NOT EXISTS (SELECT 1 FROM chat_session_events WHERE session_id = %s AND run_id = %s "
                "AND type IN ('model_input', 'delta', 'reasoning', 'tool_start', 'tool', 'steering'))",
                (session_id, run[1], session_id, run_id),
            ).fetchone()[0]
            terminal = connection.execute(
                "SELECT type FROM chat_session_events WHERE session_id = %s AND run_id = %s "
                "AND type IN ('done', 'stopped', 'error', 'stale') ORDER BY event_id DESC LIMIT 1",
                (session_id, run_id),
            ).fetchone()
            kind = terminal[0] if terminal is not None else None
            status = {"done": "completed", "stopped": "cancelled", "stale": "stale"}.get(kind, "failed")
            committed = kind == "done" or (kind != "stale" and not stopped_before_work)
            if committed and kind != "done":
                seq = connection.execute(
                    "SELECT coalesce(max(seq) + 1, 0) FROM chat_session_entries WHERE session_id = %s", (session_id,)
                ).fetchone()[0]
                _insert_entries(connection, session_id, [(seq, run_id, AssistantMessage("", "error"))])
            connection.execute(
                "UPDATE chat_runs SET status = %s, error_code = %s, committed = %s, finished_at = now() WHERE id = %s",
                (status, "service_restart" if kind is None else None, committed, run_id),
            )

    def load_session(self, session_id: str, owner: str) -> dict[str, Any] | None:
        """Load an unexpired owned session, its conversation, and the runs whose terminal event was not stored.

        As Pi's `buildSessionContext`, the conversation is rebuilt from saved entries: app
        events, proposal decisions, and the messages of committed runs. Tool results never
        join later context, so each loaded entry is one conversation entry, and the entries
        that retention trimmed from the front are skipped.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, extract(epoch FROM expires_at) FROM chat_sessions "
                "WHERE id = %s AND owner_hash = %s AND expires_at > now()",
                (session_id, _owner_hash(owner)),
            ).fetchone()
            if row is None:
                return None
            entries = connection.execute(
                "SELECT e.type, e.payload, r.status FROM chat_session_entries e LEFT JOIN chat_runs r ON r.id = e.run_id "
                "WHERE e.session_id = %s AND e.type <> 'tool_result' "
                "AND (e.run_id IS NULL OR e.type IN ('app_event', 'proposal_decision') OR r.committed) ORDER BY e.seq OFFSET %s",
                (session_id, row[0]["dropped_entries"]),
            ).fetchall()
            (next_entry_seq,) = connection.execute(
                "SELECT coalesce(max(seq) + 1, 0) FROM chat_session_entries WHERE session_id = %s", (session_id,)
            ).fetchone()
            (last_event_id,) = connection.execute(
                "SELECT coalesce(max(last_event_id), 0) FROM chat_session_events WHERE session_id = %s",
                (session_id,),
            ).fetchone()
            unfinished = connection.execute(
                "SELECT r.id, r.kind, r.status, (SELECT e.type FROM chat_session_events e "
                "WHERE e.session_id = r.session_id AND e.run_id = r.id "
                "AND e.type IN ('done', 'stopped', 'stale', 'error') ORDER BY e.event_id DESC LIMIT 1) "
                "FROM chat_runs r WHERE r.session_id = %s AND (r.status = 'running' OR NOT EXISTS ("
                "SELECT 1 FROM chat_session_events e WHERE e.session_id = r.session_id AND e.run_id = r.id "
                "AND e.type IN ('done', 'stopped', 'stale', 'error'))) ORDER BY r.sequence",
                (session_id,),
            ).fetchall()
        return {
            "state": row[0],
            "expires_at": float(row[1]),
            "entries": [
                replace(entry, stop_reason="aborted" if status == "cancelled" else "error")
                if isinstance(entry := entry_from_record(entry_type, payload), AssistantMessage)
                and status in {"failed", "cancelled", "stale"}
                else entry
                for entry_type, payload, status in entries
            ],
            "next_entry_seq": int(next_entry_seq),
            "last_event_id": int(last_event_id),
            "unfinished_runs": [
                {"id": str(run_id), "kind": kind, "status": status, "terminal_type": terminal}
                for run_id, kind, status, terminal in unfinished
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

    def export_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Read complete saved events and metadata in one consistent, read-only transaction."""
        with self._connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            session = connection.execute(
                "SELECT state, extract(epoch FROM created_at) FROM chat_sessions WHERE id = %s", (session_id,)
            ).fetchone()
            if session is None:
                return None
            runs = connection.execute(
                "SELECT r.id, r.kind, r.status, extract(epoch FROM r.started_at), "
                "extract(epoch FROM r.finished_at), "
                "(SELECT payload->>'text' FROM chat_session_entries WHERE run_id = r.id AND type = 'user' "
                "ORDER BY seq LIMIT 1) FROM chat_runs r WHERE r.session_id = %s ORDER BY r.sequence",
                (session_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT type, data, extract(epoch FROM created_at) FROM chat_session_events "
                "WHERE session_id = %s ORDER BY event_id",
                (session_id,),
            ).fetchall()
        state, created_at = session
        milliseconds = lambda timestamp: round(float(timestamp) * 1000)
        return {
            "schema_version": 1,
            "session_id": session_id,
            "snapshot_at": milliseconds(max([created_at, *(row[2] for row in events)])),
            "frontend_version": state.get("frontend_version") or "unknown",
            "metadata": state.get("export_metadata", {}),
            "pending_proposal_diff": (state.get("pending_proposal") or {}).get("diff"),
            "runs": [
                {
                    "id": str(run_id),
                    "kind": kind,
                    "status": run_status,
                    "started_at": milliseconds(started),
                    "finished_at": None if finished is None else milliseconds(finished),
                    "prompt": prompt or "",
                }
                for run_id, kind, run_status, started, finished, prompt in runs
            ],
            "events": [
                {"type": kind, "data": data, "occurred_at": milliseconds(created)} for kind, data, created in events
            ],
        }

    async def read(self, operation: str, *args):
        """Run a lookup. A failure becomes a RuntimeError that callers map to HTTP 503."""
        try:
            with anyio.CancelScope(shield=True):
                return await anyio.to_thread.run_sync(getattr(self, operation), *args)
        except (psycopg.Error, OSError):
            logger.error("AI history %s failed", operation)
            raise RuntimeError(RECOVERY_UNAVAILABLE) from None

    async def write(self, operation: str, *args, failures: RepeatedFailure | None = None, **kwargs) -> bool:
        """Report failures without leaking connection strings or chat text to logs."""
        try:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(lambda: getattr(self, operation)(*args, **kwargs))
            if failures is not None:
                ended_failures = failures.recovered()
                if ended_failures:
                    logger.warning("AI history %s resumed after %d failed attempts", operation, ended_failures)
                    report_outage_recovery(f"ai.history.{operation}", ended_failures)
            return True
        except (psycopg.Error, OSError):
            if failures is None or failures.report():
                logger.error("AI history %s failed", operation)
            return False

    async def maintain(self) -> None:
        """Apply retention hourly even when there are no chat requests."""
        while True:
            await asyncio.sleep(3600)
            await self.write("prune")


def _insert_entries(connection, session_id: str, entries: Sequence[EntryRow]) -> None:
    """Insert entries by sequence number. A retried batch keeps the first copy."""
    rows = []
    for seq, run_id, entry in entries:
        entry_type, payload = entry_record(entry)
        rows.append((session_id, seq, run_id, entry_type, _jsonb(payload)))
    if rows:
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chat_session_entries (session_id, seq, run_id, type, payload) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                rows,
            )


async def stop_maintenance(task: asyncio.Task) -> None:
    """Join the retention worker during application shutdown."""
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _migrate_legacy_transcripts(connection) -> None:
    """Preserve deployed conversation snapshots and idempotent message receipts."""
    from .context import entries_from_legacy_history

    with connection.cursor(name="ai_transcript_upgrade") as sessions:
        sessions.itersize = 100
        sessions.execute("SELECT id, state FROM chat_sessions ORDER BY id")
        for session_id, state in sessions:
            entries = (
                [entry_from_record(row["type"], row["payload"]) for row in state["transcript"]]
                if "transcript" in state
                else entries_from_legacy_history(state.get("history", []))
            )
            _insert_entries(connection, str(session_id), [(seq, None, entry) for seq, entry in enumerate(entries)])
            runs = connection.execute(
                "SELECT id, question FROM chat_runs WHERE session_id = %s ORDER BY sequence", (session_id,)
            ).fetchall()
            # Historical prompts support retries of accepted IDs. Their run entries
            # do not join context again because the snapshot already contains it.
            _insert_entries(
                connection,
                str(session_id),
                [
                    (len(entries) + seq, str(run_id), UserMessage(question))
                    for seq, (run_id, question) in enumerate(runs)
                ],
            )
            proposal = state.get("proposal_yaml")
            upgraded = {
                "schedule_yaml": state["schedule_yaml"],
                "pending_proposal": {"schedule_yaml": proposal, "diff": state.get("proposal_diff", ""), "run_id": None}
                if proposal
                else None,
                "dropped_history_messages": state.get("dropped_history_messages", 0),
                "dropped_entries": 0,
            }
            connection.execute("UPDATE chat_sessions SET state = %s WHERE id = %s", (_jsonb(upgraded), session_id))
    connection.execute("ALTER TABLE chat_runs DROP COLUMN question")
