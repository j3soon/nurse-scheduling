"""Durable text-only AI audit history in PostgreSQL."""

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
import logging
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import anyio
import psycopg
from psycopg.types.json import Jsonb

from .provider import TokenUsage

logger = logging.getLogger("nurse_scheduling.ai.history")
TurnStatus = Literal["completed", "failed", "cancelled", "stale"]


class ChatHistory:
    """Use bounded transactions off the event loop, shielded during disconnects."""

    def __init__(self, database_url: str, retention_days: int = 30) -> None:
        self._database_url = database_url
        self._retention_days = retention_days

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
        """Delete expired messages and their now-empty session metadata."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_turns WHERE started_at < now() - %s * interval '1 day'",
                (self._retention_days,),
            )
            connection.execute(
                "DELETE FROM chat_sessions s WHERE NOT EXISTS "
                "(SELECT 1 FROM chat_turns t WHERE t.session_id = s.id) "
                "AND s.created_at < now() - %s * interval '1 day'",
                (self._retention_days,),
            )

    def start_turn(
        self,
        turn_id: str,
        session_id: str,
        credential_id: str | None,
        question: str,
        model: str,
        image_count: int,
        document_count: int,
    ) -> None:
        """Atomically create a session and a uniquely identified turn."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_sessions (id, auth_credential_id) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                (session_id, credential_id),
            )
            connection.execute(
                "INSERT INTO chat_turns (id, session_id, user_message, model, image_count, document_count) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (turn_id, session_id, question, model, image_count, document_count),
            )

    def finish_turn(
        self,
        turn_id: str,
        answer: str,
        status: TurnStatus,
        error_code: str | None,
        usage: TokenUsage | None,
    ) -> None:
        """Keep the first terminal result when cleanup or writes are repeated."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE chat_turns SET assistant_message = %s, status = %s, error_code = %s, "
                "usage = %s, finished_at = now() WHERE id = %s AND status = 'running'",
                (answer, status, error_code, Jsonb(asdict(usage)) if usage else None, turn_id),
            )

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
