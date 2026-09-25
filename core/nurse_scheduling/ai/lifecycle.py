"""Event-loop-owned turn admission, cancellation and bounded streaming output."""

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
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import HTTPException

from .provider import ChatMessage


@dataclass(eq=False)
class TurnSnapshot:
    """A capability to commit one conversation version and accept its steering."""

    history: list[ChatMessage]
    schedule_yaml: str
    version: int
    proposal_yaml: str
    proposal_diff: str
    accepting_steering: bool
    previously_dropped: int = 0
    steering_queue: list[tuple[str, str]] = field(default_factory=list)
    steering_ids: set[str] = field(default_factory=set)


@dataclass(eq=False)
class Turn:
    """One operation, from admission through cleanup, independent of its HTTP reader."""

    id: str = field(default_factory=lambda: str(uuid4()))
    task: asyncio.Task[None] = field(init=False)
    ready: asyncio.Future[bool] = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    done: asyncio.Future[None] = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    cancelled: bool = False
    finishing: bool = False
    streaming: asyncio.Event = field(default_factory=asyncio.Event)
    admitted: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        # Cancellation is an edge, not a repeated interrupt of resource cleanup.
        if not self.cancelled and not self.finishing:
            self.cancelled = True
            self.task.cancel()

    async def wait(self) -> None:
        await asyncio.shield(self.done)
        self.task.result()


class SessionTurns:
    """Event-loop-owned FIFO admission. No transition below suspends.

    A foreground request is rejected while any turn owns the session. Background
    follow-ups queue behind it. Stop cancels the admitted generation, including
    queued turns, without affecting optimizer jobs that may complete later.
    """

    def __init__(self) -> None:
        self._turns: dict[str, list[Turn]] = {}
        self._closed = False

    def busy(self, session_id: str) -> bool:
        return bool(self._turns.get(session_id))

    def start(self, session_id: str, run: Callable[[Turn], Awaitable[None]], *, background: bool = False) -> Turn:
        if self._closed:
            raise HTTPException(status_code=503, detail="The AI service is shutting down.")
        pending = self._turns.setdefault(session_id, [])
        if pending and not background:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        turn = Turn()
        pending.append(turn)
        if len(pending) == 1:
            turn.admitted.set()

        async def execute() -> None:
            await turn.admitted.wait()
            await run(turn)

        def finished(task: asyncio.Task[None]) -> None:
            was_head = pending[0] is turn
            pending.remove(turn)
            if not pending:
                self._turns.pop(session_id, None)
            elif was_head:
                pending[0].admitted.set()
            if not turn.ready.done():
                turn.ready.set_result(False)
            turn.done.set_result(None)
            if not task.cancelled():
                # Retrieve even failures whose HTTP reader has already disconnected.
                task.exception()

        turn.task = asyncio.create_task(execute(), name=f"ai-turn-{turn.id}")
        turn.task.add_done_callback(finished)
        return turn

    def stop(self, session_id: str) -> None:
        for turn in tuple(self._turns.get(session_id, ())):
            turn.cancel()

    async def close(self) -> None:
        self._closed = True
        turns = [turn for pending in self._turns.values() for turn in pending]
        for turn in turns:
            turn.cancel()
        await asyncio.gather(*(turn.done for turn in turns))


class TurnEvents:
    """Bounded foreground output. Disconnect cancels work, not its cleanup."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue(maxsize=64)
        self._terminal: tuple[str, dict[str, object]] | None = None

    async def emit(self, event_type: str, data: dict[str, object]) -> None:
        # Finalization must never depend on an HTTP reader that may have left.
        if event_type in {"done", "stopped", "stale", "error"}:
            self._terminal = event_type, data
            return
        await self._queue.put((event_type, data))

    async def stream(self, turn: Turn) -> AsyncIterator[tuple[str, dict[str, object]]]:
        while True:
            if not self._queue.empty():
                yield self._queue.get_nowait()
                continue
            if turn.done.done():
                if self._terminal is not None:
                    yield self._terminal
                # Stop is a normal terminal outcome for the streaming transport.
                if not turn.task.cancelled():
                    turn.task.result()
                return
            next_event = asyncio.create_task(self._queue.get())
            try:
                await asyncio.wait((next_event, turn.done), return_when=asyncio.FIRST_COMPLETED)
                if next_event.done():
                    yield next_event.result()
            finally:
                if not next_event.done():
                    next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
