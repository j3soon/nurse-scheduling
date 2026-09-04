"""Contracts and lifecycle helpers shared by disposable sandbox providers."""

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
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("nurse_scheduling.ai.sandbox")


class SandboxError(RuntimeError):
    """A sandbox could not perform a trusted application operation."""


class SandboxCleanupError(SandboxError):
    """A sandbox could not be destroyed within the cleanup boundary."""


class SandboxFileNotFoundError(SandboxError):
    """A requested path does not exist inside an otherwise healthy sandbox."""


@dataclass(frozen=True)
class CommandResult:
    """Provider-independent result from one foreground shell command."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float = 0.0
    timed_out: bool = False


@dataclass(frozen=True)
class SandboxLifecycleMetrics:
    """Optional provider lifecycle telemetry outside the minimal backend API."""

    execution_seconds: float = 0.0
    pause_count: int = 0
    pause_cancel_count: int = 0
    pause_transition_seconds: float = 0.0
    resume_count: int = 0
    resume_wait_seconds: float = 0.0
    max_resume_wait_seconds: float = 0.0
    suspended_seconds: float = 0.0
    teardown_seconds: float = 0.0


class SandboxBackend(Protocol):
    """One disposable sandbox that survives for one complete agent turn."""

    @property
    def sandbox_id(self) -> str:
        """Return an opaque provider identifier safe for lifecycle logging."""
        ...

    async def write_file(self, path: str, content: str | bytes) -> None:
        """Create or replace one file inside the sandbox."""
        ...

    async def read_file(self, path: str) -> bytes:
        """Read one file inside the sandbox."""
        ...

    async def run(self, command: str, *, timeout_seconds: float | None = None) -> CommandResult:
        """Run one foreground shell command and return its raw result."""
        ...

    async def close(self) -> None:
        """Destroy the sandbox. Repeated calls must be safe."""
        ...


class SandboxFactory(Protocol):
    """Create a fresh provider backend for one agent turn."""

    async def create(self) -> SandboxBackend:
        """Create and return a new disposable sandbox."""
        ...


@asynccontextmanager
async def managed_sandbox(
    factory: SandboxFactory,
    *,
    cleanup_timeout_seconds: float = 10.0,
) -> AsyncIterator[SandboxBackend]:
    """Create one sandbox and destroy it without masking a turn failure."""
    if cleanup_timeout_seconds <= 0:
        raise ValueError("cleanup_timeout_seconds must be positive")

    sandbox = await factory.create()
    body_failed = False
    try:
        yield sandbox
    except BaseException:
        body_failed = True
        raise
    finally:
        try:
            await _close_sandbox(sandbox, cleanup_timeout_seconds)
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                logger.exception("Sandbox cleanup failed sandbox_id=%s", sandbox.sandbox_id)
                raise
            if body_failed:
                logger.exception("Sandbox cleanup failed sandbox_id=%s", sandbox.sandbox_id)
            else:
                raise SandboxCleanupError(f"Sandbox {sandbox.sandbox_id} could not be destroyed.") from exc


async def _close_sandbox(sandbox: SandboxBackend, timeout_seconds: float) -> None:
    """Finish cleanup even when cancellation reaches the owning request task."""

    async def close_with_timeout() -> None:
        async with asyncio.timeout(timeout_seconds):
            await sandbox.close()

    cleanup = asyncio.create_task(close_with_timeout())
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(cleanup)
        except BaseException:
            if sys.exc_info()[0] is not asyncio.CancelledError:
                logger.exception("Sandbox cleanup failed after cancellation sandbox_id=%s", sandbox.sandbox_id)
        raise
