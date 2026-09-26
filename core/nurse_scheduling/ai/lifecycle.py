"""Event-loop-owned run admission, cancellation and bounded streaming output."""

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
class RunSnapshot:
    """A capability to commit one conversation version and accept its steering."""

    history: list[ChatMessage]
    schedule_yaml: str
    version: int
    proposal_yaml: str
    proposal_diff: str
    previously_dropped: int = 0


@dataclass(eq=False)
class AgentRun:
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


class SessionRuns:
    """Event-loop-owned FIFO admission. No transition below suspends.

    A foreground request is rejected while any run owns the session. Background
    follow-ups queue behind it. Stop cancels the admitted generation, including
    queued runs, without affecting optimizer jobs that may complete later.
    """

    def __init__(self) -> None:
        self._runs: dict[str, list[AgentRun]] = {}
        self._closed = False

    def busy(self, session_id: str) -> bool:
        return bool(self._runs.get(session_id))

    def start(
        self, session_id: str, execute_run: Callable[[AgentRun], Awaitable[None]], *, background: bool = False
    ) -> AgentRun:
        if self._closed:
            raise HTTPException(status_code=503, detail="The AI service is shutting down.")
        pending = self._runs.setdefault(session_id, [])
        if pending and not background:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        run = AgentRun()
        pending.append(run)
        if len(pending) == 1:
            run.admitted.set()

        async def execute() -> None:
            await run.admitted.wait()
            await execute_run(run)

        def finished(task: asyncio.Task[None]) -> None:
            was_head = pending[0] is run
            pending.remove(run)
            if not pending:
                self._runs.pop(session_id, None)
            elif was_head:
                pending[0].admitted.set()
            if not run.ready.done():
                run.ready.set_result(False)
            run.done.set_result(None)
            if not task.cancelled():
                # Retrieve even failures whose HTTP reader has already disconnected.
                task.exception()

        run.task = asyncio.create_task(execute(), name=f"ai-run-{run.id}")
        run.task.add_done_callback(finished)
        return run

    def stop(self, session_id: str) -> None:
        for run in tuple(self._runs.get(session_id, ())):
            run.cancel()

    async def close(self) -> None:
        self._closed = True
        runs = [run for pending in self._runs.values() for run in pending]
        for run in runs:
            run.cancel()
        await asyncio.gather(*(run.done for run in runs))


class RunEvents:
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

    async def stream(self, run: AgentRun) -> AsyncIterator[tuple[str, dict[str, object]]]:
        while True:
            if not self._queue.empty():
                yield self._queue.get_nowait()
                continue
            if run.done.done():
                if self._terminal is not None:
                    yield self._terminal
                # Stop is a normal terminal outcome for the streaming transport.
                if not run.task.cancelled():
                    run.task.result()
                return
            next_event = asyncio.create_task(self._queue.get())
            try:
                await asyncio.wait((next_event, run.done), return_when=asyncio.FIRST_COMPLETED)
                if next_event.done():
                    yield next_event.result()
            finally:
                if not next_event.done():
                    next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
