"""E2B Cloud implementation of the disposable sandbox contract."""

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

import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

from e2b import AsyncSandbox
from e2b.exceptions import SandboxNotFoundException, TimeoutException
from e2b.sandbox.commands.command_handle import CommandExitException

from ..config import AiSettings
from .base import CommandResult, SandboxError

logger = logging.getLogger("nurse_scheduling.ai.sandbox.e2b")
E2B_USER = "user"
E2B_WORKSPACE = "/workspace"
COMMAND_TIMEOUT_EXIT_CODE = 124
CreateSandbox = Callable[..., Awaitable[Any]]


class E2BSandboxFactory:
    """Create one internet-disabled E2B Cloud sandbox for an agent turn."""

    def __init__(
        self,
        *,
        api_key: str,
        template: str,
        turn_timeout_seconds: float,
        command_timeout_seconds: float,
        create_sandbox: CreateSandbox | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if not template:
            raise ValueError("template must not be empty")
        if turn_timeout_seconds <= 0:
            raise ValueError("turn_timeout_seconds must be positive")
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        self._api_key = api_key
        self._template = template
        self._turn_timeout_seconds = turn_timeout_seconds
        self._command_timeout_seconds = command_timeout_seconds
        self._create_sandbox = create_sandbox or AsyncSandbox.create

    @classmethod
    def from_settings(cls, settings: AiSettings) -> "E2BSandboxFactory":
        """Create a factory from validated application settings."""
        return cls(
            api_key=settings.e2b_api_key,
            template=settings.e2b_template,
            turn_timeout_seconds=settings.sandbox_turn_timeout_seconds,
            command_timeout_seconds=settings.sandbox_command_timeout_seconds,
        )

    async def create(self) -> "E2BSandboxBackend":
        started = time.monotonic()
        try:
            sandbox = await self._create_sandbox(
                template=self._template,
                timeout=math.ceil(self._turn_timeout_seconds),
                secure=True,
                allow_internet_access=False,
                lifecycle={"on_timeout": "kill", "auto_resume": False},
                api_key=self._api_key,
            )
        except Exception as exc:
            raise SandboxError("E2B could not create a sandbox.") from exc
        backend = E2BSandboxBackend(sandbox, command_timeout_seconds=self._command_timeout_seconds)
        logger.info(
            "sandbox created sandbox_id=%s provider=e2b latency_seconds=%.3f",
            backend.sandbox_id,
            time.monotonic() - started,
        )
        return backend


class E2BSandboxBackend:
    """Expose raw E2B file, command, and lifecycle operations."""

    def __init__(self, sandbox: Any, *, command_timeout_seconds: float) -> None:
        self._sandbox = sandbox
        self._command_timeout_seconds = command_timeout_seconds
        self._closed = False
        self._commands = 0
        self._created_at = time.monotonic()

    @property
    def sandbox_id(self) -> str:
        return str(self._sandbox.sandbox_id)

    async def write_file(self, path: str, content: str | bytes) -> None:
        self._ensure_open()
        try:
            await self._sandbox.files.write(path, content, user=E2B_USER)
        except Exception as exc:
            raise SandboxError(f"E2B could not write sandbox file: {path}") from exc

    async def read_file(self, path: str) -> bytes:
        self._ensure_open()
        try:
            content = await self._sandbox.files.read(path, format="bytes", user=E2B_USER)
        except Exception as exc:
            raise SandboxError(f"E2B could not read sandbox file: {path}") from exc
        return bytes(content)

    async def run(self, command: str, *, timeout_seconds: float | None = None) -> CommandResult:
        self._ensure_open()
        timeout = timeout_seconds if timeout_seconds is not None else self._command_timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._commands += 1
        started = time.monotonic()
        try:
            result = await self._sandbox.commands.run(
                command,
                user=E2B_USER,
                cwd=E2B_WORKSPACE,
                timeout=timeout,
            )
        except CommandExitException as exc:
            result = exc
        except TimeoutException:
            destroyed = await self._close_after_timeout()
            duration = time.monotonic() - started
            logger.warning(
                "sandbox command timed out sandbox_id=%s command_number=%s duration_seconds=%.3f",
                self.sandbox_id,
                self._commands,
                duration,
            )
            cleanup = "The sandbox was destroyed." if destroyed else "Sandbox cleanup will be retried."
            return CommandResult(
                "",
                f"Command timed out after {timeout:g} seconds. {cleanup}",
                COMMAND_TIMEOUT_EXIT_CODE,
                duration_seconds=duration,
                timed_out=True,
            )
        except Exception as exc:
            raise SandboxError("E2B could not run the sandbox command.") from exc

        duration = time.monotonic() - started
        logger.info(
            "sandbox command finished sandbox_id=%s command_number=%s exit_code=%s duration_seconds=%.3f",
            self.sandbox_id,
            self._commands,
            result.exit_code,
            duration,
        )
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_seconds=duration,
        )

    async def close(self) -> None:
        if self._closed:
            return
        started = time.monotonic()
        try:
            await self._sandbox.kill()
        except SandboxNotFoundException:
            pass
        except Exception as exc:
            raise SandboxError(f"E2B could not destroy sandbox {self.sandbox_id}.") from exc
        self._closed = True
        logger.info(
            "sandbox destroyed sandbox_id=%s provider=e2b commands=%s cleanup_seconds=%.3f lifetime_seconds=%.3f",
            self.sandbox_id,
            self._commands,
            time.monotonic() - started,
            time.monotonic() - self._created_at,
        )

    async def _close_after_timeout(self) -> bool:
        try:
            await self.close()
        except SandboxError:
            logger.exception("Timed-out E2B sandbox cleanup failed sandbox_id=%s", self.sandbox_id)
            return False
        return True

    def _ensure_open(self) -> None:
        if self._closed:
            raise SandboxError(f"E2B sandbox {self.sandbox_id} is closed")
