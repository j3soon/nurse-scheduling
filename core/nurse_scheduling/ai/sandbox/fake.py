"""Deterministic fake sandbox backend for agent and lifecycle tests."""

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

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from .base import (
    CommandResult,
    SandboxError,
    SandboxFileNotFoundError,
)

CommandHandler = Callable[[str, float | None, "FakeSandboxBackend"], CommandResult | Awaitable[CommandResult]]


class FakeSandboxBackend:
    """Store files in memory and delegate commands to an injected handler."""

    def __init__(
        self,
        sandbox_id: str,
        *,
        initial_files: dict[str, bytes] | None = None,
        command_handler: CommandHandler | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self._sandbox_id = sandbox_id
        self.files = dict(initial_files or {})
        self.command_handler = command_handler
        self.close_error = close_error
        self.commands: list[tuple[str, float | None]] = []
        self.close_calls = 0
        self.closed = False

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    @asynccontextmanager
    async def activity_batch(self) -> AsyncIterator[None]:
        self._ensure_open()
        yield

    async def write_file(self, path: str, content: str | bytes) -> None:
        self._ensure_open()
        self.files[path] = content.encode() if isinstance(content, str) else content

    async def read_file(self, path: str) -> bytes:
        self._ensure_open()
        try:
            content = self.files[path]
        except KeyError as exc:
            raise SandboxFileNotFoundError(f"Sandbox file not found: {path}") from exc
        return content

    async def run(self, command: str, *, timeout_seconds: float | None = None) -> CommandResult:
        self._ensure_open()
        self.commands.append((command, timeout_seconds))
        if self.command_handler is None:
            result = CommandResult("", "Command is not configured in the fake sandbox.", 127)
        else:
            pending = self.command_handler(command, timeout_seconds, self)
            result = await pending if inspect.isawaitable(pending) else pending
        return result

    async def close(self) -> None:
        self.close_calls += 1
        if self.closed:
            return
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def _ensure_open(self) -> None:
        if self.closed:
            raise SandboxError(f"Sandbox {self.sandbox_id} is closed")


class FakeSandboxFactory:
    """Return a new isolated fake backend for every create call."""

    def __init__(
        self,
        backend_factory: Callable[[str], FakeSandboxBackend] | None = None,
        *,
        create_error: BaseException | None = None,
    ) -> None:
        self.backend_factory = backend_factory or FakeSandboxBackend
        self.create_error = create_error
        self.created: list[FakeSandboxBackend] = []

    async def create(self) -> FakeSandboxBackend:
        if self.create_error is not None:
            raise self.create_error
        backend = self.backend_factory(f"fake-{len(self.created) + 1}")
        self.created.append(backend)
        return backend
