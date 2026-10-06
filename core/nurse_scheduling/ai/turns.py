"""Turn execution and complete replay state independent of browser connections."""

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
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field

TERMINAL_EVENTS = frozenset({"done", "stopped", "stale", "error"})


def append_compacted(events: list[dict], event_type: str, data: dict) -> None:
    """Retain complete text without keeping one snapshot entry per token."""
    if event_type in {"delta", "reasoning"} and events and events[-1]["type"] == event_type:
        events[-1]["data"]["text"] += data["text"]
    elif event_type == "context_usage" and events and events[-1]["type"] == event_type:
        events[-1]["data"] = deepcopy(data)
    else:
        events.append({"type": event_type, "data": deepcopy(data)})


@dataclass
class ReplayTurn:
    id: str
    session_id: str
    request_id: str
    question: str
    events: list[dict] = field(default_factory=list)
    recent: deque = field(default_factory=lambda: deque(maxlen=1000))
    cursor: int = 0
    terminal: bool = False
    retired: bool = False
    signal: asyncio.Event = field(default_factory=asyncio.Event)

    def append(self, event_id: int, event_type: str, data: dict) -> None:
        self.cursor = event_id
        self.recent.append((event_id, event_type, deepcopy(data)))
        append_compacted(self.events, event_type, data)
        self.terminal = event_type in TERMINAL_EVENTS
        self.signal.set()

    async def stream(self, cursor: int, snapshot: bool = False):
        """Replay missed events or send complete output when a cursor is too old."""
        if snapshot:
            cursor = self.cursor
            yield cursor, "turn_snapshot", {"events": deepcopy(self.events)}
            if self.terminal:
                return
        if self.terminal and cursor >= self.cursor:
            yield self.recent[-1]
            return
        while True:
            if self.retired:
                return
            if self.recent and cursor < self.recent[0][0] - 1:
                cursor = self.cursor
                yield cursor, "turn_snapshot", {"events": deepcopy(self.events)}
            else:
                for event in tuple(self.recent):
                    if event[0] > cursor:
                        cursor = event[0]
                        yield event
            if self.terminal and cursor >= self.cursor:
                return
            if cursor < self.cursor:
                continue
            self.signal.clear()
            try:
                await asyncio.wait_for(self.signal.wait(), timeout=15)
            except TimeoutError:
                yield None


class TurnJournal:
    """Keep accepted questions and complete output beyond the bounded SSE buffer."""

    def __init__(self) -> None:
        self.turns: dict[tuple[str, str], ReplayTurn] = {}
        self.stopped_requests: set[tuple[str, str]] = set()

    async def request_stop(self, session_id: str, request_id: str) -> None:
        self.stopped_requests.add((session_id, request_id))

    async def was_stopped(self, session_id: str, request_id: str) -> bool:
        return (session_id, request_id) in self.stopped_requests

    async def get(self, session_id: str, request_id: str) -> ReplayTurn | None:
        return self.turns.get((session_id, request_id))

    async def start(self, session_id: str, turn_id: str, request_id: str, question: str) -> ReplayTurn:
        turn = ReplayTurn(turn_id, session_id, request_id, question)
        self.turns[session_id, request_id] = turn
        return turn

    async def publish(self, turn: ReplayTurn, event_type: str, data: dict) -> None:
        turn.append(turn.cursor + 1, event_type, data)

    async def finish(self, turn: ReplayTurn, event_type: str, data: dict) -> None:
        turn.append(turn.cursor + 1, event_type, data)

    def forget_session(self, session_id: str) -> None:
        self.stopped_requests = {key for key in self.stopped_requests if key[0] != session_id}
        for key in tuple(self.turns):
            if key[0] == session_id:
                turn = self.turns.pop(key)
                turn.retired = True
                turn.signal.set()
