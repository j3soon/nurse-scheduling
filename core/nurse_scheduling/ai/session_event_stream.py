"""Replayable background events and optimizer progress."""

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
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .turns import append_compacted


@dataclass(frozen=True)
class SessionEvent:
    """One replayable event from an assistant turn initiated by background work."""

    id: int
    type: str
    data: dict[str, object]


class SessionEventBroker:
    """Process-local replay for background turns and independent optimizer progress."""

    def __init__(
        self,
        max_events_per_session: int = 1000,
        max_sessions: int = 1000,
        max_progress_events_per_session: int = 100,
        max_snapshot_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self._max_events_per_session = max_events_per_session
        self._max_progress_events_per_session = max_progress_events_per_session
        self._max_sessions = max_sessions
        self._events: dict[str, list[SessionEvent]] = {}
        self._progress_events: dict[str, list[SessionEvent]] = {}
        self._last_ids: dict[str, int] = {}
        self._signals: dict[str, asyncio.Event] = {}
        self._snapshots: dict[str, list[dict]] = {}
        self._evicted_ids: dict[str, int] = {}
        self._publish_locks: dict[str, asyncio.Lock] = {}
        self.on_publish = None
        self.load_snapshot = None
        self._snapshot_incomplete: set[str] = set()
        self._snapshot_bytes: dict[str, int] = {}
        self._max_snapshot_bytes = max_snapshot_bytes

    async def emit(
        self, session_id: str, event_type: str, data: dict[str, object], *, metadata: dict | None = None
    ) -> None:
        lock = self._publish_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            if self._publish_locks.get(session_id) is not lock:
                return
            event_id = self._last_ids.get(session_id, 0) + 1
            if self.on_publish is not None and event_type != "optimization_progress":
                if metadata is None:
                    await self.on_publish(session_id, event_id, event_type, data)
                else:
                    await self.on_publish(session_id, event_id, event_type, data, metadata)
            if self._publish_locks.get(session_id) is lock:
                self.publish(session_id, event_type, data)

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
        if event_type != "optimization_progress" and session_id not in self._snapshot_incomplete:
            append_compacted(self._snapshots.setdefault(session_id, []), event_type, data)
            self._snapshot_bytes[session_id] = self._snapshot_bytes.get(session_id, 0) + len(json.dumps(data).encode())
            if sum(self._snapshot_bytes.values()) > self._max_snapshot_bytes:
                if self.load_snapshot is not None:
                    self._snapshots.pop(session_id, None)
                    self._snapshot_bytes.pop(session_id, None)
                    self._snapshot_incomplete.add(session_id)
                else:
                    self._trim_snapshot(session_id)
        limit = (
            self._max_progress_events_per_session
            if event_type == "optimization_progress"
            else self._max_events_per_session
        )
        if event_type != "optimization_progress" and len(events) > limit:
            self._evicted_ids[session_id] = max(self._evicted_ids.get(session_id, 0), events[-limit - 1].id)
        del events[:-limit]
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def _trim_snapshot(self, session_id: str) -> None:
        """Without recovery storage, drop a session's oldest output until the snapshots fit.

        Trim to three quarters of the budget, so a full cache does not measure the
        snapshot again on every event.
        """
        snapshot = self._snapshots[session_id]
        sizes = [len(json.dumps(entry["data"]).encode()) for entry in snapshot]
        others = sum(self._snapshot_bytes.values()) - self._snapshot_bytes[session_id]
        retained = sum(sizes)
        dropped = 0
        while dropped < len(sizes) - 1 and others + retained > self._max_snapshot_bytes * 3 // 4:
            retained -= sizes[dropped]
            dropped += 1
        del snapshot[:dropped]
        self._snapshot_bytes[session_id] = retained

    def forget_session(self, session_id: str) -> None:
        self._events.pop(session_id, None)
        self._progress_events.pop(session_id, None)
        self._last_ids.pop(session_id, None)
        self._snapshots.pop(session_id, None)
        self._snapshot_bytes.pop(session_id, None)
        self._snapshot_incomplete.discard(session_id)
        self._evicted_ids.pop(session_id, None)
        self._publish_locks.pop(session_id, None)
        # Wake an open stream so it observes the dropped signal and ends, instead of
        # recreating the entry this pop removes and waiting on a retired session.
        signal = self._signals.pop(session_id, None)
        if signal is not None:
            signal.set()

    def restore(self, session_id: str, events: list[dict]) -> None:
        if events and events[0].get("first_id", events[0]["id"]) > 1:
            self._snapshot_incomplete.add(session_id)
            self._evicted_ids[session_id] = events[0]["id"] - 1
        for event in events:
            self._last_ids[session_id] = event["id"] - 1
            self.publish(session_id, event["type"], event["data"])
        if events:
            # Recovery entries contain accumulated text, so replay them as a replacement.
            self._evicted_ids[session_id] = events[-1]["id"]

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Return retained events after a cursor for replay and diagnostics."""
        retained = (*self._events.get(session_id, ()), *self._progress_events.get(session_id, ()))
        return tuple(sorted((event for event in retained if event.id > after_id), key=lambda event: event.id))

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        signal = self._signals.setdefault(session_id, asyncio.Event())
        while True:
            if self._signals.get(session_id) is not signal:
                return
            if after_id < self._evicted_ids.get(session_id, 0) or after_id > self._last_ids.get(session_id, 0):
                if session_id in self._snapshot_incomplete and self.load_snapshot is not None:
                    after_id, events = await self.load_snapshot(session_id)
                else:
                    after_id = self._last_ids.get(session_id, 0)
                    events = self._snapshots.get(session_id, [])
                yield SessionEvent(after_id, "session_snapshot", {"events": events})
                continue
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
