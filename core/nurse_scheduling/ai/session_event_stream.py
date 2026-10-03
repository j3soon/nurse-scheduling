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
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from .lifecycle import TERMINAL_EVENTS

# Serialized JSON bytes, including event IDs and types. SSE framing is added by HTTP.
DEFAULT_SESSION_REPLAY_BYTES = 4 * 1024 * 1024
DEFAULT_TOTAL_REPLAY_BYTES = 64 * 1024 * 1024
REPLACEABLE_EVENTS = frozenset({"optimization_progress", "context_usage", "schedule_change"})


@dataclass(frozen=True)
class SessionEvent:
    """One immutable publication in a session's ordered event history."""

    id: int
    type: str
    data: dict[str, object]
    bytes: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bytes", len(json.dumps(self.payload(), ensure_ascii=False).encode()))

    def payload(self) -> dict[str, object]:
        return {"id": self.id, "type": self.type, "data": self.data}


@dataclass
class _Replay:
    events: list[SessionEvent] = field(default_factory=list)
    # Recovery folds adjacent text fragments and replaces disposable state updates.
    recovery: list[SessionEvent] = field(default_factory=list)
    last_id: int = 0
    lost_through: int = 0
    incomplete: bool = False
    bytes: int = 0


def _replacement_key(event: SessionEvent) -> tuple[str, object] | None:
    if event.type not in REPLACEABLE_EVENTS:
        return None
    return event.type, event.data.get("job_id" if event.type == "optimization_progress" else "run_id")


class SessionEventStream:
    """Event-loop-owned bounded replay. Readers never hold up execution.

    Each session has a journal and a recovery projection, each bounded by count
    and serialized JSON bytes. Their combined size also has a process-wide cap.
    IDs survive eviction. Lost required events request a reset to the recovery
    projection, while replaced progress/preview IDs do not create a replay gap.
    """

    def __init__(
        self,
        max_events_per_session: int = 1000,
        max_sessions: int = 1000,
        max_progress_events_per_session: int = 100,
        max_bytes_per_session: int = DEFAULT_SESSION_REPLAY_BYTES,
        max_total_bytes: int = DEFAULT_TOTAL_REPLAY_BYTES,
    ) -> None:
        if (
            min(
                max_events_per_session,
                max_sessions,
                max_progress_events_per_session,
                max_bytes_per_session,
                max_total_bytes,
            )
            <= 0
        ):
            raise ValueError("Replay limits must be positive")
        self._max_events = max_events_per_session
        self._max_progress = max_progress_events_per_session
        self._max_sessions = max_sessions
        self._max_bytes = max_bytes_per_session
        self._max_total_bytes = max_total_bytes
        self._sessions: dict[str, _Replay] = {}
        self._signals: dict[str, asyncio.Event] = {}
        self._retained_bytes = 0

    def publish(self, session_id: str, event_type: str, data: dict[str, object]) -> None:
        if session_id not in self._sessions and len(self._sessions) >= self._max_sessions:
            self.forget_session(next(iter(self._sessions)))
        replay = self._sessions.setdefault(session_id, _Replay())
        # Copy JSON data so a publisher cannot later mutate the retained payload.
        replay.last_id += 1
        event = SessionEvent(replay.last_id, event_type, json.loads(json.dumps(data)))
        key = _replacement_key(event)
        if key is not None:
            replay.events = [old for old in replay.events if _replacement_key(old) != key]
        replay.events.append(event)
        self._recover(replay, event)
        self._trim(replay)
        self._charge(replay)
        self._trim_total()
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def _recover(self, replay: _Replay, event: SessionEvent) -> None:
        key = _replacement_key(event)
        # Optimizer state is a checkpoint. The journal retains lifecycle transitions.
        if event.type == "optimization":
            replay.recovery = [
                old
                for old in replay.recovery
                if not (old.type == "optimization" and old.data.get("job_id") == event.data.get("job_id"))
            ]
        elif key is not None:
            replay.recovery = [old for old in replay.recovery if _replacement_key(old) != key]
        if replay.recovery and event.type in {"delta", "reasoning"}:
            last = replay.recovery[-1]
            if last.type == event.type and last.data.get("run_id") == event.data.get("run_id"):
                event = SessionEvent(
                    event.id,
                    event.type,
                    {**event.data, "text": str(last.data.get("text", "")) + str(event.data.get("text", ""))},
                )
                replay.recovery.pop()
        replay.recovery.append(event)

    def _drop(self, replay: _Replay, events: list[SessionEvent], index: int, *, recovery: bool = False) -> None:
        event = events.pop(index)
        if recovery:
            replay.incomplete = True
        elif event.type not in REPLACEABLE_EVENTS:
            replay.lost_through = max(replay.lost_through, event.id)

    @staticmethod
    def _eviction_index(events: list[SessionEvent]) -> int:
        # Evict completed output before active work and keep its outcome longest.
        completed = {event.data.get("run_id") for event in events if event.type in TERMINAL_EVENTS}
        for index, event in enumerate(events):
            if event.data.get("run_id") in completed and event.type not in TERMINAL_EVENTS:
                return index
        for index, event in enumerate(events):
            if event.type in REPLACEABLE_EVENTS:
                return index
        return 0

    def _trim(self, replay: _Replay) -> None:
        for events, recovery in [(replay.events, False), (replay.recovery, True)]:
            for progress, limit in [(False, self._max_events), (True, self._max_progress)]:
                while sum((event.type == "optimization_progress") == progress for event in events) > limit:
                    eligible = [event for event in events if (event.type == "optimization_progress") == progress]
                    index = events.index(eligible[self._eviction_index(eligible)])
                    self._drop(replay, events, index, recovery=recovery)
            while sum(event.bytes for event in events) > self._max_bytes:
                self._drop(replay, events, self._eviction_index(events), recovery=recovery)

    def _charge(self, replay: _Replay) -> None:
        size = sum(event.bytes for event in (*replay.events, *replay.recovery))
        self._retained_bytes += size - replay.bytes
        replay.bytes = size

    def _trim_total(self) -> None:
        while self._retained_bytes > self._max_total_bytes:
            # Choose completed session output first, then the oldest retained output.
            candidates = [r for r in self._sessions.values() if r.bytes]
            replay = next((r for r in candidates if any(e.type in TERMINAL_EVENTS for e in r.events)), candidates[0])
            recovery = not replay.events
            events = replay.recovery if recovery else replay.events
            self._drop(replay, events, self._eviction_index(events), recovery=recovery)
            self._charge(replay)

    def forget_session(self, session_id: str) -> None:
        replay = self._sessions.pop(session_id, None)
        if replay is not None:
            self._retained_bytes -= replay.bytes
        signal = self._signals.pop(session_id, None)
        if signal is not None:
            signal.set()

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Retained journal entries for diagnostics. Streaming also detects gaps."""
        replay = self._sessions.get(session_id)
        return tuple(event for event in replay.events if event.id > after_id) if replay else ()

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        signal = self._signals.setdefault(session_id, asyncio.Event())
        while self._signals.get(session_id) is signal:
            replay = self._sessions.get(session_id)
            if replay is not None and (after_id < replay.lost_through or after_id > replay.last_id):
                after_id = replay.last_id
                yield SessionEvent(
                    after_id,
                    "session_reset",
                    {
                        "events": [event.payload() for event in replay.recovery],
                        "incomplete": replay.incomplete,
                    },
                )
                continue
            event = next((event for event in replay.events if event.id > after_id), None) if replay else None
            if event is not None:
                # Recheck after every yield. A slow reader must not hold a batch of
                # evicted payloads or silently continue over newly expired history.
                after_id = event.id
                yield event
                continue
            signal.clear()
            try:
                await asyncio.wait_for(signal.wait(), timeout=15)
            except TimeoutError:
                yield None
