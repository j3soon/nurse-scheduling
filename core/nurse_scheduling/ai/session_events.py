"""Replayable session events for background runs and optimizer progress."""

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

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionEvent:
    """One replayable event from an assistant run initiated by background work."""

    id: int
    type: str
    data: dict[str, object]


class SessionEventBroker:
    """Process-local replay for background runs and independent optimizer progress."""

    def __init__(
        self,
        max_events_per_session: int = 1000,
        max_sessions: int = 1000,
        max_progress_events_per_session: int = 100,
    ) -> None:
        self._max_events_per_session = max_events_per_session
        self._max_progress_events_per_session = max_progress_events_per_session
        self._max_sessions = max_sessions
        self._events: dict[str, list[SessionEvent]] = {}
        self._progress_events: dict[str, list[SessionEvent]] = {}
        self._last_ids: dict[str, int] = {}
        self._signals: dict[str, asyncio.Event] = {}

    def publish(self, session_id: str, event_type: str, data: dict[str, object]) -> None:
        if session_id not in self._events and len(self._events) >= self._max_sessions:
            oldest_session_id = next(iter(self._events))
            self.forget_session(oldest_session_id)
        self._events.setdefault(session_id, [])
        events = (
            self._progress_events.setdefault(session_id, [])
            if event_type == "optimization_progress"
            else self._events[session_id]
        )
        event_id = self._last_ids.get(session_id, 0) + 1
        self._last_ids[session_id] = event_id
        events.append(SessionEvent(event_id, event_type, data))
        limit = (
            self._max_progress_events_per_session
            if event_type == "optimization_progress"
            else self._max_events_per_session
        )
        del events[:-limit]
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def forget_session(self, session_id: str) -> None:
        self._events.pop(session_id, None)
        self._progress_events.pop(session_id, None)
        self._last_ids.pop(session_id, None)
        # Wake an open stream so it observes the dropped signal and ends, instead of
        # recreating the entry this pop removes and waiting on a retired session.
        signal = self._signals.pop(session_id, None)
        if signal is not None:
            signal.set()

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Return retained events after a cursor for replay and diagnostics."""
        retained = (*self._events.get(session_id, ()), *self._progress_events.get(session_id, ()))
        return tuple(sorted((event for event in retained if event.id > after_id), key=lambda event: event.id))

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        signal = self._signals.setdefault(session_id, asyncio.Event())
        while True:
            pending = self.events_after(session_id, after_id)
            if pending:
                for event in pending:
                    after_id = event.id
                    yield event
                continue
            if self._signals.get(session_id) is not signal:
                return
            signal.clear()
            try:
                await asyncio.wait_for(signal.wait(), timeout=15)
            except TimeoutError:
                yield None
