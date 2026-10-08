"""Complete chat recovery entries and execution metadata in PostgreSQL."""

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
from contextlib import suppress
from pathlib import Path
from typing import Literal

import anyio
import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger("nurse_scheduling.ai.history")
TurnStatus = Literal["completed", "failed", "cancelled", "stale"]
TERMINAL_STATUSES: dict[str, TurnStatus] = {
    "done": "completed",
    "error": "failed",
    "stopped": "cancelled",
    "stale": "stale",
}


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
        """Delete expired sessions, including their turns, entries, and Stop requests."""
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_recovery_sessions WHERE expires_at < now()")

    def save_recovery_session(
        self, session_id: str, owner: str, expires_at: float, state: dict, credential_id: str | None = None
    ) -> None:
        """Keep session ownership and schedule context for message recovery."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_recovery_sessions (id, owner_hash, expires_at, state, auth_credential_id) "
                "VALUES (%s, %s, to_timestamp(%s), %s, %s) ON CONFLICT (id) DO UPDATE SET "
                "expires_at = EXCLUDED.expires_at, state = EXCLUDED.state",
                (session_id, hashlib.sha256(owner.encode()).hexdigest(), expires_at, Jsonb(state), credential_id),
            )

    def stop_recovery_request(self, session_id: str, request_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_recovery_stops (session_id, request_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (session_id, request_id),
            )

    def recovery_request_stopped(self, session_id: str, request_id: str) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM chat_recovery_stops WHERE session_id = %s AND request_id = %s",
                    (session_id, request_id),
                ).fetchone()
                is not None
            )

    def start_recovery_turn(
        self, turn_id: str, session_id: str, request_id: str | None, question: str, metadata: dict | None = None
    ) -> None:
        metadata = metadata or {}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_recovery_turns (id, session_id, request_id, question, kind, auth_credential_id, model, attachment_count) "
                "VALUES (%s, %s, %s, %s, %s, coalesce(%s, (SELECT auth_credential_id FROM chat_recovery_sessions WHERE id = %s)), %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (
                    turn_id,
                    session_id,
                    request_id,
                    question,
                    metadata.get("kind", "foreground"),
                    metadata.get("auth_credential_id"),
                    session_id,
                    metadata.get("model", ""),
                    metadata.get("attachment_count", 0),
                ),
            )

    def append_recovery_event(self, session_id: str, channel: str, event_id: int, event_type: str, data: dict) -> None:
        with self._connect() as connection:
            self._append_recovery_entry(connection, session_id, channel, event_id, event_type, data)

    @staticmethod
    def _append_recovery_entry(
        connection, session_id: str, channel: str, event_id: int, event_type: str, data: dict
    ) -> str | None:
        from .turns import append_compacted

        # Serialize foreground and background writes before choosing an entry to extend.
        connection.execute("SELECT id FROM chat_recovery_sessions WHERE id = %s FOR UPDATE", (session_id,))
        previous = connection.execute(
            "SELECT channel, event_id, last_event_id, event_type, data FROM chat_recovery_entries "
            "WHERE session_id = %s ORDER BY sequence DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        same_channel = previous is not None and previous[0] == channel
        last_cursor = previous[2] if same_channel else 0
        if previous is not None and not same_channel:
            row = connection.execute(
                "SELECT last_event_id FROM chat_recovery_entries WHERE session_id = %s AND channel = %s "
                "ORDER BY event_id DESC LIMIT 1",
                (session_id, channel),
            ).fetchone()
            last_cursor = row[0] if row else 0
        if event_id <= last_cursor:
            return None
        turn = connection.execute(
            "SELECT id FROM chat_recovery_turns WHERE session_id = %s "
            "AND (id::text = %s OR (%s = 'background' AND kind = 'background' AND status = 'running')) "
            "ORDER BY sequence DESC LIMIT 1",
            (session_id, channel, channel),
        ).fetchone()
        turn_id = str(turn[0]) if turn and event_type != "optimization" else None
        if same_channel and previous[3] == event_type and event_type in {"delta", "reasoning", "context_usage"}:
            entries = [{"type": event_type, "data": previous[4]}]
            append_compacted(entries, event_type, data)
            connection.execute(
                "UPDATE chat_recovery_entries SET last_event_id = %s, data = %s "
                "WHERE session_id = %s AND channel = %s AND event_id = %s",
                (event_id, Jsonb(entries[0]["data"]), session_id, channel, previous[1]),
            )
        else:
            connection.execute(
                "INSERT INTO chat_recovery_entries (session_id, channel, turn_id, event_id, last_event_id, event_type, data) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (session_id, channel, turn_id, event_id, event_id, event_type, Jsonb(data)),
            )
        if event_type in TERMINAL_STATUSES:
            connection.execute(
                "UPDATE chat_recovery_turns SET status = %s, finished_at = now() WHERE id = %s AND status = 'running'",
                (TERMINAL_STATUSES[event_type], turn_id),
            )
        return turn_id

    def finish_recovery_turn(
        self,
        session_id: str,
        owner: str,
        expires_at: float,
        state: dict,
        channel: str,
        event_id: int,
        event_type: str,
        data: dict,
        metadata: dict | None = None,
    ) -> None:
        """Commit conversation context and its terminal acknowledgement together."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE chat_recovery_sessions SET expires_at = to_timestamp(%s), state = %s "
                "WHERE id = %s AND owner_hash = %s",
                (expires_at, Jsonb(state), session_id, hashlib.sha256(owner.encode()).hexdigest()),
            )
            turn_id = self._append_recovery_entry(connection, session_id, channel, event_id, event_type, data)
            if turn_id is not None and metadata is not None:
                connection.execute(
                    "UPDATE chat_recovery_turns SET error_code = %s, usage = %s WHERE id = %s",
                    (metadata.get("error_code"), Jsonb(metadata["usage"]) if metadata.get("usage") else None, turn_id),
                )

    def load_recovery_session(self, session_id: str, owner: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, extract(epoch FROM expires_at) FROM chat_recovery_sessions "
                "WHERE id = %s AND owner_hash = %s AND expires_at > now()",
                (session_id, hashlib.sha256(owner.encode()).hexdigest()),
            ).fetchone()
            if row is None:
                return None
            turns = connection.execute(
                "SELECT id, request_id, question FROM chat_recovery_turns "
                "WHERE session_id = %s AND kind = 'foreground' AND status = 'running' ORDER BY sequence",
                (session_id,),
            ).fetchall()
            background = connection.execute(
                "SELECT status FROM chat_recovery_turns WHERE session_id = %s AND kind = 'background' ORDER BY sequence DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            events = connection.execute(
                "SELECT channel, event_id, last_event_id, event_type, data FROM chat_recovery_entries e "
                "WHERE session_id = %s AND (channel = 'background' AND last_event_id > "
                "(SELECT coalesce(max(last_event_id), 0) - 1000 FROM chat_recovery_entries "
                "WHERE session_id = e.session_id AND channel = 'background') "
                "OR channel IN (SELECT id::text FROM chat_recovery_turns t WHERE t.session_id = e.session_id "
                "AND t.kind = 'foreground' AND t.status = 'running')) ORDER BY channel, event_id",
                (session_id,),
            ).fetchall()
        channels: dict[str, list[dict]] = {}
        for channel, first_id, last_id, event_type, data in events:
            channels.setdefault(channel, []).append(
                {"first_id": first_id, "id": last_id, "type": event_type, "data": data}
            )
        return {
            "state": row[0],
            "expires_at": float(row[1]),
            "background_status": background[0] if background else None,
            "turns": [
                {
                    "id": str(turn_id),
                    "request_id": request_id,
                    "question": question,
                    "events": channels.get(str(turn_id), []),
                }
                for turn_id, request_id, question in turns
            ],
            "background_events": channels.get("background", []),
        }

    def load_recovery_turn(self, session_id: str, request_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, question FROM chat_recovery_turns WHERE session_id = %s AND request_id = %s",
                (session_id, request_id),
            ).fetchone()
            if row is None:
                return None
            events = connection.execute(
                "SELECT event_id, last_event_id, event_type, data FROM chat_recovery_entries "
                "WHERE session_id = %s AND channel = %s ORDER BY event_id",
                (session_id, str(row[0])),
            )
            return {
                "id": str(row[0]),
                "request_id": request_id,
                "question": row[1],
                "events": [
                    {"first_id": first_id, "id": last_id, "type": event_type, "data": data}
                    for first_id, last_id, event_type, data in events
                ],
            }

    def load_background_snapshot(self, session_id: str) -> tuple[int, list[dict]]:
        from .turns import append_compacted

        events = []
        last_id = 0
        with self._connect() as connection:
            for event_id, event_type, data in connection.execute(
                "SELECT last_event_id, event_type, data FROM chat_recovery_entries "
                "WHERE session_id = %s AND channel = 'background' ORDER BY event_id",
                (session_id,),
            ):
                last_id = event_id
                append_compacted(events, event_type, data)
        return last_id, events

    async def read(self, operation: str, *args):
        try:
            with anyio.CancelScope(shield=True):
                return await anyio.to_thread.run_sync(getattr(self, operation), *args)
        except (psycopg.Error, OSError):
            logger.error("AI history %s failed", operation)
            raise RuntimeError("AI message recovery is temporarily unavailable.") from None

    async def write(self, operation: str, *args) -> bool:
        """Report failures without leaking connection strings or chat text to logs."""
        try:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(getattr(self, operation), *args)
            return True
        except (psycopg.Error, OSError):
            logger.error("AI history %s failed", operation)
            return False

    async def maintain(self) -> None:
        """Apply retention hourly even when there are no chat requests."""
        while True:
            await asyncio.sleep(3600)
            await self.write("prune")


async def stop_maintenance(task: asyncio.Task) -> None:
    """Join the retention worker during application shutdown."""
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
