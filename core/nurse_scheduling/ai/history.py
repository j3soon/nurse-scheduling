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
from .context import ABORTED_RESPONSE_HISTORY, interrupted_entries
from .costs import CostTotals
from .provider import ProviderCall, TokenUsage
from .transcript import (
    AgentMessage,
    AppEventEntry,
    AssistantMessage,
    CompactionEntry,
    ToolResultMessage,
    UserMessage,
    entry_from_record,
    entry_record,
)
from .workspace import SandboxAttachment, attachment_path

logger = logging.getLogger("nurse_scheduling.ai.history")
RunStatus = Literal["completed", "failed", "cancelled", "stale"]
RunKind = Literal["foreground", "background", "compaction"]
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
        """Delete expired sessions with their uploads, runs, entries, events, and Stop requests."""
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_sessions WHERE expires_at < now()")

    @staticmethod
    def _save_state(
        connection,
        session_id: str,
        state: SessionState,
        entries: Sequence[EntryRow],
        credential_id: str | None = None,
        uploads: Sequence[SandboxAttachment] = (),
        downloads: dict[str, bytes | None] | None = None,
        files: Sequence[dict] = (),
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
        retained_files = [
            {
                "kind": "upload",
                "source_id": upload.id,
                "filename": upload.filename,
                "media_type": upload.media_type,
                "data": upload.data,
            }
            for upload in uploads
            if upload.data is not None
        ]
        retained_files.extend(
            {
                "kind": "download",
                "source_id": run_id,
                "run_id": run_id,
                "filename": "download.zip",
                "media_type": "application/zip",
                "data": content,
            }
            for run_id, content in (downloads or {}).items()
            if content is not None
        )
        # Save detached versions first, so an active upload that reuses their source ID stays current.
        ChatHistory._save_files(connection, session_id, [*files, *retained_files])
        for kind, active in (
            ("upload", [upload["id"] for upload in data.get("uploads", [])]),
            ("download", data.get("downloads", [])),
        ):
            connection.execute(
                "UPDATE chat_files SET removed_at = now() WHERE session_id = %s AND kind = %s "
                "AND removed_at IS NULL AND NOT (source_id = ANY(%s::text[]))",
                (session_id, kind, active),
            )

    @staticmethod
    def _save_files(connection, session_id: str, files: Sequence[dict]) -> None:
        for file in files:
            # Reusing a detached source ID preserves the old file version.
            connection.execute(
                "UPDATE chat_files SET removed_at = now() WHERE session_id = %s AND kind = %s "
                "AND source_id = %s AND removed_at IS NULL AND "
                "(data <> %s OR filename <> %s OR media_type <> %s)",
                (session_id, file["kind"], file["source_id"], file["data"], file["filename"], file["media_type"]),
            )
            connection.execute(
                "INSERT INTO chat_files (session_id, kind, source_id, filename, media_type, data, run_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (session_id, kind, source_id) WHERE removed_at IS NULL DO NOTHING",
                (
                    session_id,
                    file["kind"],
                    file["source_id"],
                    file["filename"],
                    file["media_type"],
                    file["data"],
                    file.get("run_id"),
                ),
            )

    def save_session(
        self,
        session_id: str,
        state: SessionState,
        credential_id: str | None = None,
        *,
        entries: Sequence[EntryRow] = (),
        uploads: Sequence[SandboxAttachment] = (),
        downloads: dict[str, bytes | None] | None = None,
        files: Sequence[dict] = (),
    ) -> None:
        """Keep session ownership, expiry, schedule, and new conversation entries."""
        with self._connect() as connection:
            self._save_state(connection, session_id, state, entries, credential_id, uploads, downloads, files)

    def append_entries(self, session_id: str, entries: Sequence[EntryRow]) -> None:
        """Save entries as they end, as Pi saves each message on `message_end`."""
        with self._connect() as connection:
            _insert_entries(connection, session_id, entries)

    def start_run(
        self,
        run_id: str,
        session_id: str,
        state: SessionState,
        prompt: str | None,
        prompt_seq: int,
        *,
        model: str,
        attachment_count: int,
        kind: RunKind = "foreground",
        message_id: str | None = None,
        credential_id: str | None = None,
        entries: Sequence[EntryRow] = (),
        uploads: Sequence[SandboxAttachment] = (),
        downloads: dict[str, bytes | None] | None = None,
        files: Sequence[dict] = (),
    ) -> None:
        """Atomically save the session state, a uniquely identified run, and its prompt entry.

        The prompt is written before model work, so it survives a process that dies mid-run.
        """
        with self._connect() as connection:
            self._save_state(connection, session_id, state, entries, uploads=uploads, downloads=downloads, files=files)
            inserted = connection.execute(
                "INSERT INTO chat_runs (id, session_id, model, attachment_count, kind, message_id, auth_credential_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, "
                "coalesce(%s, (SELECT auth_credential_id FROM chat_sessions WHERE id = %s))) "
                "ON CONFLICT (id) DO NOTHING RETURNING id",
                (run_id, session_id, model, attachment_count, kind, message_id, credential_id, session_id),
            ).fetchone()
            if inserted is not None and prompt is not None:
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
        schedule_change: dict[str, Any] | None = None,
        uploads: Sequence[SandboxAttachment] = (),
        downloads: dict[str, bytes | None] | None = None,
        files: Sequence[dict] = (),
    ) -> None:
        """Commit the run outcome with the resulting session state, keeping the first terminal result.

        `committed` records whether the run's messages joined the session conversation.
        """
        with self._connect() as connection:
            self._save_state(connection, session_id, state, entries, uploads=uploads, downloads=downloads, files=files)
            connection.execute(
                "UPDATE chat_runs SET status = %s, error_code = %s, usage = %s, committed = %s, "
                "schedule_change = %s, finished_at = now() "
                "WHERE id = %s AND status = 'running'",
                (
                    status,
                    error_code,
                    Jsonb(asdict(usage)) if usage else None,
                    committed,
                    _jsonb(schedule_change) if schedule_change is not None else None,
                    run_id,
                ),
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
                "SELECT r.id, CASE WHEN r.kind = 'compaction' THEN '/compact' ELSE e.payload->>'text' END FROM chat_runs r "
                "LEFT JOIN chat_session_entries e ON e.run_id = r.id AND e.type = 'user' "
                "WHERE r.session_id = %s AND r.message_id = %s ORDER BY e.seq LIMIT 1",
                (session_id, message_id),
            ).fetchone()
        return None if row is None else (str(row[0]), row[1])

    def recover_run(self, session_id: str, run_id: str) -> None:
        """Retain safe context for an accepted run that a dead process left unfinished."""
        with self._connect() as connection:
            connection.execute("SELECT id FROM chat_sessions WHERE id = %s FOR UPDATE", (session_id,))
            run = connection.execute(
                "SELECT status, message_id, kind FROM chat_runs WHERE id = %s AND session_id = %s FOR UPDATE",
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
            committed = kind == "done" or (run[2] != "compaction" and kind != "stale" and not stopped_before_work)
            if committed and kind != "done":
                _recover_run_context(connection, session_id, run_id)
            connection.execute(
                "UPDATE chat_runs SET status = %s, error_code = %s, committed = %s, finished_at = now() WHERE id = %s",
                (status, "service_restart" if kind is None else None, committed, run_id),
            )

    def load_session(self, session_id: str, owner: str) -> dict[str, Any] | None:
        """Load an unexpired owned session, its conversation, and the runs whose terminal event was not stored.

        As Pi's `buildSessionContext`, the conversation is rebuilt from saved entries: app
        events, proposal decisions, and the messages of committed runs. The entries
        that retention trimmed from the front are skipped.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, extract(epoch FROM expires_at), auth_credential_id FROM chat_sessions "
                "WHERE id = %s AND owner_hash = %s AND expires_at > now()",
                (session_id, _owner_hash(owner)),
            ).fetchone()
            if row is None:
                return None
            # Saved totals can be newer than a failed call checkpoint. Apply only
            # later publications, replacing calls that were pending in that snapshot.
            version = row[0].get("cost_totals_version", -1)
            totals = CostTotals.restored(row[0].get("cost_totals") if version >= 0 else None)
            pending = {call["id"]: ProviderCall(**call) for call in row[0].get("pending_provider_calls", [])}
            costs = connection.execute(
                "WITH calls AS (SELECT DISTINCT ON (data->>'call_id') event_id, data "
                "FROM chat_session_events WHERE session_id = %s AND type = 'provider_call' "
                "ORDER BY data->>'call_id', event_id DESC) "
                "SELECT event_id, data FROM calls WHERE event_id > %s ORDER BY event_id",
                (session_id, version),
            ).fetchall()
            for event_id, data in costs:
                call_id, amount = data["call_id"], data.get("cost_usd")
                final = ProviderCall(call_id, "", "reported" if amount is not None else "unavailable", amount)
                totals.update(final, pending.pop(call_id, None))
                version = max(version, event_id)
            for call in pending.values():
                totals.update(replace(call, status="reported" if call.cost_usd is not None else "unavailable"), call)
            if costs or "cost_totals" in row[0]:
                row[0]["cost_totals"] = totals.public()
                row[0]["cost_totals_version"] = max(version, 0)
                row[0]["pending_provider_calls"] = []
            entries = connection.execute(
                "SELECT e.type, e.payload FROM chat_session_entries e LEFT JOIN chat_runs r ON r.id = e.run_id "
                "WHERE e.session_id = %s "
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
            (archive_bytes,) = connection.execute(
                "SELECT coalesce(sum(octet_length(data)), 0) FROM chat_files WHERE session_id = %s", (session_id,)
            ).fetchone()
            removed_uploads = connection.execute(
                "SELECT DISTINCT source_id, filename FROM chat_files WHERE session_id = %s "
                "AND kind = 'upload' AND removed_at IS NOT NULL",
                (session_id,),
            ).fetchall()
            unfinished = connection.execute(
                "SELECT r.id, r.kind, r.status, r.schedule_change, (SELECT e.type FROM chat_session_events e "
                "WHERE e.session_id = r.session_id AND e.run_id = r.id "
                "AND e.type IN ('done', 'stopped', 'stale', 'error') ORDER BY e.event_id DESC LIMIT 1) "
                "FROM chat_runs r WHERE r.session_id = %s AND (r.status = 'running' OR NOT EXISTS ("
                "SELECT 1 FROM chat_session_events e WHERE e.session_id = r.session_id AND e.run_id = r.id "
                "AND e.type IN ('done', 'stopped', 'stale', 'error'))) ORDER BY r.sequence",
                (session_id,),
            ).fetchall()
        return {
            "state": row[0],
            "credential_id": row[2],
            "uploads": [SandboxAttachment(data=None, **metadata) for metadata in row[0].get("uploads", [])],
            "removed_upload_paths": [
                attachment_path(SandboxAttachment(filename, "", None, id=upload_id), 0)
                for upload_id, filename in removed_uploads
            ],
            "expires_at": float(row[1]),
            "entries": [entry_from_record(kind, payload) for kind, payload in entries],
            "next_entry_seq": int(next_entry_seq),
            "last_event_id": int(last_event_id),
            "archive_bytes": int(archive_bytes),
            "unfinished_runs": [
                {
                    "id": str(run_id),
                    "kind": kind,
                    "status": status,
                    "terminal_type": terminal,
                    "schedule_change": schedule_change,
                }
                for run_id, kind, status, schedule_change, terminal in unfinished
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

    def load_upload(self, session_id: str, owner: str, upload_id: str, size_bytes: int) -> bytes | None:
        """Read one owned, unexpired file whose byte count still matches its saved metadata."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT u.data FROM chat_files u JOIN chat_sessions s ON s.id = u.session_id "
                "WHERE u.session_id = %s AND u.source_id = %s AND u.kind = 'upload' AND u.removed_at IS NULL AND s.owner_hash = %s AND s.expires_at > now() "
                "AND octet_length(u.data) = %s",
                (session_id, upload_id, _owner_hash(owner), size_bytes),
            ).fetchone()
        return None if row is None else row[0]

    def load_file(self, session_id: str, owner: str, kind: str, source_id: str) -> bytes | None:
        """Read one active generated file of an owned, unexpired session."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT f.data FROM chat_files f JOIN chat_sessions s ON s.id = f.session_id "
                "WHERE f.session_id = %s AND s.owner_hash = %s AND s.expires_at > now() "
                "AND f.kind = %s AND f.source_id = %s AND f.removed_at IS NULL",
                (session_id, _owner_hash(owner), kind, source_id),
            ).fetchone()
        return None if row is None else row[0]

    def latest_optimizer(self, session_id: str, owner: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                # A terminal update survives even when a storage limit refused all of that job's files.
                "SELECT f.source_id FROM ("
                "SELECT session_id, source_id, created_at, NULL::bigint AS event_id "
                "FROM chat_files WHERE kind = 'optimizer-status' "
                "UNION ALL SELECT session_id, data->>'job_id', created_at, event_id FROM chat_session_events "
                "WHERE type = 'optimization' AND data->>'terminal' = 'true'"
                ") f JOIN chat_sessions s ON s.id = f.session_id "
                "WHERE f.session_id = %s AND s.owner_hash = %s AND s.expires_at > now() "
                "ORDER BY f.created_at DESC, f.event_id DESC NULLS LAST LIMIT 1",
                (session_id, _owner_hash(owner)),
            ).fetchone()
        return None if row is None else row[0]

    @staticmethod
    def export_snapshot(connection, session_id: str) -> dict[str, Any] | None:
        """Read complete saved events and metadata through the caller's consistent read-only transaction."""
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
            logger.exception("AI history %s failed", operation)
            raise RuntimeError(RECOVERY_UNAVAILABLE) from None

    async def write(self, operation: str, *args, failures: RepeatedFailure | None = None, **kwargs) -> bool:
        """Run a write. A failure is logged with its exception and returns False."""
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
                logger.exception("AI history %s failed", operation)
            return False

    async def maintain(self) -> None:
        """Apply retention hourly even when there are no chat requests."""
        while True:
            await asyncio.sleep(3600)
            await self.write("prune")


def _recover_run_context(connection, session_id: str, run_id: str) -> None:
    """Repair stored context and its public events in the same recovery transaction."""
    rows = connection.execute(
        "SELECT seq, type, payload FROM chat_session_entries WHERE session_id = %s AND run_id = %s ORDER BY seq",
        (session_id, run_id),
    ).fetchall()
    original = [entry_from_record(entry_type, payload) for _seq, entry_type, payload in rows]
    repaired = interrupted_entries(original, "error")
    known_tools = {id(entry) for entry in original if isinstance(entry, ToolResultMessage)}
    missing = [entry for entry in repaired if isinstance(entry, ToolResultMessage) and id(entry) not in known_tools]
    last = next(
        (
            (seq, entry)
            for (seq, _kind, _payload), entry in zip(reversed(rows), reversed(original), strict=True)
            # Shutdown finalization saves the notice after an answer row that already exists.
            if not isinstance(entry, CompactionEntry)
            and not (isinstance(entry, AppEventEntry) and entry.text == ABORTED_RESPONSE_HISTORY)
        ),
        None,
    )
    final_answer = last is not None and isinstance(last[1], AssistantMessage) and not last[1].tool_calls
    # Final validation may not have run before the process stopped, and an interrupted run's summary is not applied.
    marked = [
        (seq, run_id, replace(entry, valid=False))
        for (seq, _kind, _payload), entry in zip(rows, original, strict=True)
        if isinstance(entry, CompactionEntry) and entry.valid
    ]
    if final_answer:
        marked.append((last[0], run_id, replace(last[1], stop_reason="error")))
    _insert_entries(connection, session_id, marked)
    appended = [*missing]
    if not final_answer:
        appended.append(AssistantMessage("", "error"))
    if not any(isinstance(entry, AppEventEntry) and entry.text == ABORTED_RESPONSE_HISTORY for entry in original):
        appended.append(AppEventEntry(ABORTED_RESPONSE_HISTORY))
    seq = connection.execute(
        "SELECT coalesce(max(seq) + 1, 0) FROM chat_session_entries WHERE session_id = %s", (session_id,)
    ).fetchone()[0]
    _insert_entries(
        connection,
        session_id,
        [(seq + offset, run_id, entry) for offset, entry in enumerate(appended)],
    )
    calls = {call.id: call for entry in original if isinstance(entry, AssistantMessage) for call in entry.tool_calls}
    events = [
        {
            "type": "tool",
            "tool_call_id": entry.tool_call_id,
            "name": entry.tool_name,
            "arguments": calls[entry.tool_call_id].arguments,
            "result": entry.text,
            "ok": False,
        }
        for entry in missing
    ]
    if not connection.execute(
        "SELECT EXISTS (SELECT 1 FROM chat_session_events WHERE session_id = %s AND run_id = %s "
        "AND type = 'response_end' AND data ? 'context_note')",
        (session_id, run_id),
    ).fetchone()[0]:
        events.append({"type": "response_end", "stop_reason": "error", "context_note": ABORTED_RESPONSE_HISTORY})
    event_id = connection.execute(
        "SELECT coalesce(max(last_event_id), 0) FROM chat_session_events WHERE session_id = %s",
        (session_id,),
    ).fetchone()[0]
    for offset, event in enumerate(events, 1):
        event_type = event.pop("type")
        connection.execute(
            "INSERT INTO chat_session_events (session_id, event_id, last_event_id, run_id, type, data) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                session_id,
                event_id + offset,
                event_id + offset,
                run_id,
                event_type,
                _jsonb({**event, "run_id": run_id}),
            ),
        )


def _insert_entries(connection, session_id: str, entries: Sequence[EntryRow]) -> None:
    """Save entries by sequence number.

    A later copy of a run's entry can change only its interruption state. Other conflicts keep the first copy.
    """
    rows = []
    for seq, run_id, entry in entries:
        entry_type, payload = entry_record(entry)
        rows.append((session_id, seq, run_id, entry_type, _jsonb(payload)))
    if rows:
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chat_session_entries AS e (session_id, seq, run_id, type, payload) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id, seq) DO UPDATE SET payload = EXCLUDED.payload "
                "WHERE e.run_id = EXCLUDED.run_id AND e.type = EXCLUDED.type AND e.payload <> EXCLUDED.payload "
                "AND e.payload - 'stop_reason' - 'valid' = EXCLUDED.payload - 'stop_reason' - 'valid'",
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
