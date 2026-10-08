"""Event-loop-owned run scheduling, cancellation and owned cleanup."""

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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import HTTPException

from .candidate import PendingProposal
from .transcript import AgentMessage
from .workspace import SandboxAttachment

# Each run publishes exactly one of these, after its cleanup, whichever transport carries it.
TERMINAL_EVENTS = frozenset({"done", "stopped", "stale", "error"})


@dataclass(eq=False)
class RunSnapshot:
    """A capability to commit one conversation version and accept its steering."""

    transcript: list[AgentMessage]
    schedule_yaml: str
    version: int
    pending_proposal: PendingProposal | None
    previously_dropped: int = 0
    run_id: str | None = None
    # Uploads cannot change while a run is active, so this stays valid for the whole run.
    uploads: tuple[SandboxAttachment, ...] = ()


@dataclass(eq=False)
class AgentRun:
    """One operation, from acceptance through cleanup, independent of its HTTP reader."""

    id: str = field(default_factory=lambda: str(uuid4()))
    # The client message ID of a foreground run, which a named Stop and a retried POST match.
    message_id: str | None = None
    task: asyncio.Task[None] = field(init=False)
    ready: asyncio.Future[bool] = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    done: asyncio.Future[None] = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    cancelled: bool = False
    # The session started executing the run, so it publishes the run's terminal outcome.
    begun: bool = False
    finishing: bool = False
    # Service shutdown cancelled the run. Recovery reports it as a restart, not a user Stop.
    shutdown: bool = False
    ready_to_start: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        # Cancellation is an edge, not a repeated interrupt of resource cleanup.
        if not self.cancelled and not self.finishing:
            self.cancelled = True
            self.task.cancel()

    async def wait(self) -> None:
        await asyncio.shield(self.done)
        self.task.result()


class SessionRuns:
    """Event-loop-owned FIFO execution. No transition below suspends.

    A foreground request is rejected while any run owns the session. Background
    follow-ups queue behind it. Stop cancels active and queued runs, without
    affecting optimizer jobs that may complete later. A Stop that names a client
    message cancels only that message's run, so a delayed Stop cannot end a later run.
    """

    def __init__(self) -> None:
        self._runs: dict[str, list[AgentRun]] = {}
        self._closed = False

    def busy(self, session_id: str) -> bool:
        return bool(self._runs.get(session_id))

    def start(
        self,
        session_id: str,
        execute_run: Callable[[AgentRun], Awaitable[None]],
        *,
        background: bool = False,
        message_id: str | None = None,
    ) -> AgentRun:
        if self._closed:
            raise HTTPException(status_code=503, detail="The AI service is shutting down.")
        pending = self._runs.setdefault(session_id, [])
        if pending and not background:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        run = AgentRun(message_id=message_id)
        pending.append(run)
        if len(pending) == 1:
            run.ready_to_start.set()

        async def execute() -> None:
            await run.ready_to_start.wait()
            await execute_run(run)

        def finished(task: asyncio.Task[None]) -> None:
            was_head = pending[0] is run
            pending.remove(run)
            if not pending:
                self._runs.pop(session_id, None)
            elif was_head:
                pending[0].ready_to_start.set()
            if not run.ready.done():
                run.ready.set_result(False)
            run.done.set_result(None)
            if not task.cancelled():
                # Retrieve even failures whose HTTP reader has already disconnected.
                task.exception()

        run.task = asyncio.create_task(execute(), name=f"ai-run-{run.id}")
        run.task.add_done_callback(finished)
        return run

    def stop(self, session_id: str, message_id: str | None = None) -> None:
        for run in tuple(self._runs.get(session_id, ())):
            if message_id is None or run.message_id == message_id:
                run.cancel()

    async def close(self) -> None:
        self._closed = True
        runs = [run for pending in self._runs.values() for run in pending]
        for run in runs:
            # A run that a user already stopped keeps its Stop outcome.
            if not run.cancelled:
                run.shutdown = True
                run.cancel()
        await asyncio.gather(*(run.done for run in runs))
