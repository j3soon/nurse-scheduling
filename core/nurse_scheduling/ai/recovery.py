"""Preserve legacy chat recovery while execution is organized by session."""

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

# This file is mostly AI generated.

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException

from .history import ChatHistory
from .session_event_stream import SessionEventBroker
from .turns import TurnJournal

if TYPE_CHECKING:
    from .sessions import SessionStore


class SessionRecovery:
    """Own legacy replay, ordered state writes, restoration, and eviction pins."""

    def __init__(
        self,
        store: SessionStore,
        history_log: ChatHistory | None,
        event_broker: SessionEventBroker,
        turn_journal: TurnJournal,
    ):
        self.store = store
        self.history_log = history_log
        self.event_broker = event_broker
        self.turn_journal = turn_journal
        self.state_write_locks: dict[str, asyncio.Lock] = {}
        self.session_pins: Counter[str] = Counter()
        self.unsaved_sessions: set[str] = set()
        self.recovery_lock = asyncio.Lock()
        self.shutting_down = False
        event_broker.on_publish = self.persist_background_event
        if history_log is not None:
            event_broker.load_snapshot = lambda session_id: history_log.read("load_background_snapshot", session_id)

    def forget_session(self, session_id: str) -> None:
        self.state_write_locks.pop(session_id, None)
        self.unsaved_sessions.discard(session_id)
        self.event_broker.forget_session(session_id)
        self.turn_journal.forget_session(session_id)

    def evictable(self, session_id: str) -> bool:
        return (
            session_id not in self.session_pins
            and session_id not in self.unsaved_sessions
            and not self.turn_journal.has_unsaved_outcome(session_id)
        )

    def state_write_lock(self, session_id: str) -> asyncio.Lock:
        """Serialize each state capture with its write, so an older state never commits last."""
        return self.state_write_locks.setdefault(session_id, asyncio.Lock())

    def pin_session(self, session_id: str) -> Callable[..., None]:
        """Keep a session loaded until the returned release runs.

        The store marks a session idle before its worker saves the outcome, and an
        endpoint changes a session before its write starts. Eviction must wait for both.
        """
        self.session_pins[session_id] += 1

        def release(*_args: object) -> None:
            self.session_pins[session_id] -= 1
            if self.session_pins[session_id] <= 0:
                del self.session_pins[session_id]

        return release

    def record_save(self, session_id: str, saved: bool) -> bool:
        """Keep a session whose newest state failed to save, so eviction never drops its only copy."""
        if saved:
            self.unsaved_sessions.discard(session_id)
        elif session_id in self.store._sessions:
            self.unsaved_sessions.add(session_id)
        return saved

    async def save_session(self, session_id: str, credential_id: str | None = None) -> bool:
        if self.history_log is None:
            return True
        release = self.pin_session(session_id)
        try:
            async with self.state_write_lock(session_id):
                if session_id not in self.store._sessions:
                    return True
                recovery_state = self.store.recovery_state(session_id)
                saved = await self.turn_journal.save_outcomes(
                    session_id, recovery_state
                ) and await self.history_log.write("save_recovery_session", session_id, *recovery_state, credential_id)
                return self.record_save(session_id, saved)
        finally:
            release()

    async def restore_session(self, session_id: str, owner: str | None) -> None:
        try:
            self.store.require_owned(session_id, owner)
            return
        except HTTPException as exc:
            if exc.status_code != 404 or self.history_log is None or owner is None:
                raise
        async with self.recovery_lock:
            if session_id in self.store._sessions:
                self.store.require_owned(session_id, owner)
                return
            try:
                try:
                    UUID(session_id)
                    UUID(owner)
                except ValueError:
                    raise HTTPException(status_code=404, detail="Chat session not found.") from None
                record = await self.history_log.read("load_recovery_session", session_id, owner)
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
            if record is None:
                raise HTTPException(status_code=404, detail="Chat session not found.")
            self.store.restore(session_id, owner, record)
            release = self.pin_session(session_id)
            try:
                for turn in self.turn_journal.restore(session_id, record["turns"]):
                    if not turn.terminal:
                        async with self.state_write_lock(session_id):
                            saved = await self.turn_journal.finish(
                                turn,
                                "error",
                                {
                                    "message": "The AI service restarted during this response. Your question and saved output were recovered. You can retry this turn."
                                },
                                state=self.store.recovery_state(session_id),
                                metadata={"error_code": "service_restart"},
                            )
                            self.record_save(session_id, saved)
                self.event_broker.restore(session_id, record["background_events"])
                if record["background_status"] == "running":
                    await self.event_broker.emit(
                        session_id,
                        "error",
                        {
                            "message": "The AI service restarted during this background response. Its saved output was recovered."
                        },
                        metadata={"error_code": "service_restart"},
                    )
            finally:
                release()

    async def persist_background_event(
        self, session_id: str, event_id: int, event_type: str, data: dict, metadata: dict | None = None
    ) -> None:
        if self.history_log is None:
            return
        # Deliver terminal and optimizer status events even when saving fails. Otherwise an
        # outage leaves the browser waiting and stops the optimizer from waking the agent.
        if event_type in {"done", "stopped", "stale", "error"}:
            if event_type == "stopped" and self.shutting_down:
                return
            async with self.state_write_lock(session_id):
                if session_id not in self.store._sessions:
                    return
                saved = await self.history_log.write(
                    "finish_recovery_turn",
                    session_id,
                    *self.store.recovery_state(session_id),
                    "background",
                    event_id,
                    event_type,
                    data,
                    metadata,
                )
                self.record_save(session_id, saved)
            return
        if event_type == "optimization":
            if await self.save_session(session_id):
                await self.history_log.write(
                    "append_recovery_event", session_id, "background", event_id, event_type, data
                )
            return
        if event_type == "turn_start" and not await self.save_session(session_id):
            raise RuntimeError("AI message recovery is temporarily unavailable.")
        if not await self.history_log.write(
            "append_recovery_event", session_id, "background", event_id, event_type, data
        ):
            raise RuntimeError("AI message recovery is temporarily unavailable.")
