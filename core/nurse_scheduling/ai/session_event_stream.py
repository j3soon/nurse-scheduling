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
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import TypedDict

from .lifecycle import TERMINAL_EVENTS
from .session_events import AgentSessionEvent

# Serialized JSON bytes, including event IDs and types. SSE framing is added by HTTP.
DEFAULT_SESSION_REPLAY_BYTES = 4 * 1024 * 1024
DEFAULT_TOTAL_REPLAY_BYTES = 64 * 1024 * 1024
REPLACEABLE_EVENTS = frozenset({"optimization_progress", "context_usage", "schedule_change"})
# A restored stream continues this far past its last stored ID. A browser cursor from the
# previous process can be ahead of storage, and must still fall inside the replaced range.
RESTORE_CURSOR_GAP = 1_000_000


class SessionEventPayload(TypedDict):
    """Serialized event included in a recovery snapshot."""

    id: int
    type: str
    data: dict[str, object]


class SessionResetData(TypedDict):
    """Recovery fields produced by the stream before HTTP adds session state."""

    events: list[SessionEventPayload]
    incomplete: bool


@dataclass(frozen=True)
class SessionEvent:
    """One immutable publication in a session's ordered event history."""

    id: int
    type: str
    data: dict[str, object]
    bytes: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bytes", len(json.dumps(self.payload(), ensure_ascii=False).encode()))

    def payload(self) -> SessionEventPayload:
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
    # The last stored ID when the session was restored, or None for a session of this process.
    restored_through: int | None = None


def _replacement_key(event: SessionEvent) -> tuple[str, object] | None:
    if event.type not in REPLACEABLE_EVENTS:
        return None
    return event.type, event.data.get("job_id" if event.type == "optimization_progress" else "run_id")


def _fold(recovery: list[SessionEvent], event: SessionEvent) -> list[SessionEvent]:
    """Add one event to a recovery projection and return the updated projection."""
    key = _replacement_key(event)
    # Optimizer state is a checkpoint. The journal retains lifecycle transitions.
    if event.type == "optimization":
        recovery = [
            old
            for old in recovery
            if not (old.type == "optimization" and old.data.get("job_id") == event.data.get("job_id"))
        ]
    elif key is not None:
        recovery = [old for old in recovery if _replacement_key(old) != key]
    if recovery and event.type in {"delta", "reasoning"}:
        last = recovery[-1]
        if last.type == event.type and last.data.get("run_id") == event.data.get("run_id"):
            event = SessionEvent(
                event.id,
                event.type,
                {**event.data, "text": str(last.data.get("text", "")) + str(event.data.get("text", ""))},
            )
            recovery.pop()
    recovery.append(event)
    return recovery


def fold_recovery(events: Iterable[SessionEvent]) -> list[SessionEvent]:
    """Project stored events the same way as the live recovery projection."""
    recovery: list[SessionEvent] = []
    for event in events:
        recovery = _fold(recovery, event)
    return recovery


class SessionEventStream:
    """Event-loop-owned bounded replay. Readers never hold up execution.

    Each session has a journal and a recovery projection, each bounded by count
    and serialized JSON bytes. Their combined size also has a process-wide cap.
    IDs survive eviction. Lost required events request a reset to the recovery
    projection, while replaced progress/preview IDs do not create a replay gap.

    With recovery storage, `observer` receives each publication for saving, and
    `load_recovery` supplies a complete reset when the projection lost output or
    the session was restored after a restart.
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
        self._signals: dict[str, set[asyncio.Event]] = {}
        self._retained_bytes = 0
        self.observer: Callable[[str, SessionEvent], None] | None = None
        # Return the last covered event ID and the stored recovery events after a cursor,
        # or None when storage cannot serve them.
        self.load_recovery: Callable[[str, int], Awaitable[tuple[int, list[SessionEvent]] | None]] | None = None

    def publish(self, session_id: str, publication: AgentSessionEvent) -> None:
        if session_id not in self._sessions and len(self._sessions) >= self._max_sessions:
            self.forget_session(next(iter(self._sessions)))
        replay = self._sessions.setdefault(session_id, _Replay())
        # Copy JSON data so a publisher cannot later mutate the retained payload.
        replay.last_id += 1
        data = {key: value for key, value in publication.items() if key != "type"}
        event = SessionEvent(replay.last_id, publication["type"], json.loads(json.dumps(data)))
        key = _replacement_key(event)
        if key is not None:
            replay.events = [old for old in replay.events if _replacement_key(old) != key]
        replay.events.append(event)
        replay.recovery = _fold(replay.recovery, event)
        self._trim(replay)
        self._charge(replay)
        self._trim_total()
        if self.observer is not None:
            self.observer(session_id, event)
        for signal in self._signals.get(session_id, ()):
            signal.set()

    def restore(self, session_id: str, stored_through: int) -> None:
        """Continue a restored session's IDs past storage and serve every reset from storage."""
        self.forget_session(session_id)
        last_id = stored_through + RESTORE_CURSOR_GAP
        self._sessions[session_id] = _Replay(
            last_id=last_id, lost_through=last_id, incomplete=True, restored_through=stored_through
        )

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

    async def _reset(self, session_id: str, replay: _Replay, after_id: int) -> SessionEvent:
        """Build a reset from the projection, or from storage when the projection is incomplete."""
        stored = None
        if self.load_recovery is not None and replay.incomplete:
            if replay.restored_through is not None and after_id < replay.restored_through + RESTORE_CURSOR_GAP:
                # A cursor of the previous process may include output that storage never received.
                # Replace the newest stored run as well.
                after_id = min(after_id, replay.restored_through - 1)
            stored = await self.load_recovery(session_id, after_id)
        if stored is not None:
            last_id, events = stored
            data: SessionResetData = {"events": [event.payload() for event in events], "incomplete": False}
            return SessionEvent(last_id, "session_reset", dict(data))
        data = {"events": [event.payload() for event in replay.recovery], "incomplete": replay.incomplete}
        return SessionEvent(replay.last_id, "session_reset", dict(data))

    def forget_session(self, session_id: str) -> None:
        replay = self._sessions.pop(session_id, None)
        if replay is not None:
            self._retained_bytes -= replay.bytes
        for signal in self._signals.pop(session_id, ()):
            signal.set()

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Retained journal entries for diagnostics. Streaming also detects gaps."""
        replay = self._sessions.get(session_id)
        return tuple(event for event in replay.events if event.id > after_id) if replay else ()

    def cursor(self, session_id: str) -> int:
        replay = self._sessions.get(session_id)
        return replay.last_id if replay is not None else 0

    async def stream(self, session_id: str, after_id: int) -> AsyncGenerator[SessionEvent | None]:
        signal = asyncio.Event()
        self._signals.setdefault(session_id, set()).add(signal)
        try:
            while signal in self._signals.get(session_id, ()):
                replay = self._sessions.get(session_id)
                if replay is not None and (after_id < replay.lost_through or after_id > replay.last_id):
                    reset = await self._reset(session_id, replay, after_id)
                    after_id = reset.id
                    yield reset
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
        finally:
            readers = self._signals.get(session_id)
            if readers is not None:
                readers.discard(signal)
                if not readers:
                    self._signals.pop(session_id, None)
