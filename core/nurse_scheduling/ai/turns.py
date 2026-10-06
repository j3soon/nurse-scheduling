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
import json
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .history import ChatHistory

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
    restored_cursor: int = 0
    terminal: bool = False
    retired: bool = False
    durable_terminal: bool = False
    signal: asyncio.Event = field(default_factory=asyncio.Event)

    def append(self, event_id: int, event_type: str, data: dict) -> None:
        self.cursor = event_id
        self.recent.append((event_id, event_type, deepcopy(data)))
        append_compacted(self.events, event_type, data)
        self.terminal = event_type in TERMINAL_EVENTS
        self.signal.set()

    async def stream(self, cursor: int, snapshot: bool = False):
        """Replay missed events or send complete output when a cursor is too old."""
        # Stored entries can contain text both before and after the client's cursor.
        if snapshot or cursor < self.restored_cursor:
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

    def __init__(self, history: ChatHistory | None, max_cached_bytes: int = 256 * 1024 * 1024) -> None:
        self.history = history
        self.max_cached_bytes = max_cached_bytes
        self.turns: dict[tuple[str, str], ReplayTurn] = {}
        self.stopped_requests: set[tuple[str, str]] = set()

    async def request_stop(self, session_id: str, request_id: str) -> None:
        if self.history is not None and not await self.history.write("stop_recovery_request", session_id, request_id):
            raise RuntimeError("The stop request could not be saved. Please try again.")
        self.stopped_requests.add((session_id, request_id))

    async def was_stopped(self, session_id: str, request_id: str) -> bool:
        if (session_id, request_id) in self.stopped_requests:
            return True
        if self.history is not None:
            return bool(await self.history.read("recovery_request_stopped", session_id, request_id))
        return False

    async def get(self, session_id: str, request_id: str) -> ReplayTurn | None:
        turn = self.turns.get((session_id, request_id))
        if turn is None and self.history is not None:
            record = await self.history.read("load_recovery_turn", session_id, request_id)
            if record is not None:
                turn = self.restore(session_id, [record])[0]
                self.trim_cache()
        return turn

    def trim_cache(self) -> None:
        if self.history is None:
            return
        sizes = {
            key: len(json.dumps(turn.events).encode())
            + len(json.dumps(list(turn.recent)).encode())
            + len(turn.question.encode())
            for key, turn in self.turns.items()
        }
        retained = sum(sizes.values())
        for key, turn in tuple(self.turns.items()):
            if retained <= self.max_cached_bytes:
                break
            if turn.durable_terminal:
                del self.turns[key]
                retained -= sizes[key]

    async def start(
        self, session_id: str, turn_id: str, request_id: str, question: str, metadata: dict | None = None
    ) -> ReplayTurn:
        turn = ReplayTurn(turn_id, session_id, request_id, question)
        self.turns[session_id, request_id] = turn
        if self.history is not None and not await self.history.write(
            "start_recovery_turn", turn_id, session_id, request_id, question, metadata
        ):
            self.turns.pop((session_id, request_id), None)
            raise RuntimeError("AI message recovery is temporarily unavailable.")
        return turn

    async def publish(self, turn: ReplayTurn, event_type: str, data: dict) -> None:
        event_id = turn.cursor + 1
        if self.history is not None and not await self.history.write(
            "append_recovery_event", turn.session_id, turn.id, event_id, event_type, data
        ):
            raise RuntimeError("AI message recovery is temporarily unavailable.")
        turn.append(event_id, event_type, data)
        if turn.terminal:
            turn.durable_terminal = self.history is not None
            self.trim_cache()

    async def finish(
        self, turn: ReplayTurn, event_type: str, data: dict, *, state: tuple, metadata: dict | None = None
    ) -> None:
        event_id = turn.cursor + 1
        persisted = self.history is not None
        data = deepcopy(data)
        if persisted and event_type == "done":
            data["history_saved"] = True
        if self.history is not None and not await self.history.write(
            "finish_recovery_turn", turn.session_id, *state, turn.id, event_id, event_type, data, metadata
        ):
            turn.append(
                event_id,
                "warning",
                {"message": "This response could not be saved for recovery after a service restart."},
            )
            event_id += 1
            persisted = False
            if event_type == "done":
                data["history_saved"] = False
        turn.append(event_id, event_type, data)
        turn.durable_terminal = persisted
        self.trim_cache()

    def restore(self, session_id: str, records: list[dict[str, Any]]) -> list[ReplayTurn]:
        restored = []
        for record in records:
            turn = ReplayTurn(record["id"], session_id, record["request_id"], record["question"])
            for event in record["events"]:
                turn.append(event["id"], event["type"], event["data"])
            turn.restored_cursor = turn.cursor
            turn.durable_terminal = turn.terminal
            self.turns[session_id, turn.request_id] = turn
            restored.append(turn)
        return restored

    def forget_session(self, session_id: str) -> None:
        self.stopped_requests = {key for key in self.stopped_requests if key[0] != session_id}
        for key in tuple(self.turns):
            if key[0] == session_id:
                turn = self.turns.pop(key)
                turn.retired = True
                turn.signal.set()
