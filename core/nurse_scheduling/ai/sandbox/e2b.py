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

import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, TypeVar

from e2b import AsyncSandbox
from e2b.exceptions import (
    AuthenticationException,
    FileNotFoundException,
    InvalidArgumentException,
    NotEnoughSpaceException,
    NotFoundException,
    SandboxException,
    SandboxNotFoundException,
    TemplateException,
    TimeoutException,
)
from e2b.sandbox.commands.command_handle import CommandExitException

from ..config import AiSettings
from .base import CommandResult, SandboxError, SandboxFileNotFoundError, SandboxLifecycleMetrics
from .e2b_cleanup import E2BSandboxCleanupManager

logger = logging.getLogger("nurse_scheduling.ai.sandbox.e2b")
E2B_USER = "user"
E2B_WORKSPACE = "/workspace"
COMMAND_TIMEOUT_EXIT_CODE = 124
CreateSandbox = Callable[..., Awaitable[Any]]
RequestResult = TypeVar("RequestResult")
NON_RETRYABLE_E2B_ERRORS = (
    AuthenticationException,
    InvalidArgumentException,
    NotEnoughSpaceException,
    NotFoundException,
    TemplateException,
)


def _is_retryable_e2b_error(error: BaseException) -> bool:
    return isinstance(error, TimeoutError) or (
        isinstance(error, SandboxException) and not isinstance(error, NON_RETRYABLE_E2B_ERRORS)
    )


async def _retry_e2b_request(
    operation: Callable[[], Awaitable[RequestResult]],
    *,
    operation_name: str,
    sandbox_id: str,
    max_attempts: int,
    backoff_seconds: float,
) -> RequestResult:
    """Retry replay-safe E2B requests without logging response contents."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not _is_retryable_e2b_error(error) or attempt == max_attempts:
                raise
            delay = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "E2B request failed operation=%s sandbox_id=%s attempt=%s max_attempts=%s "
                "retry_in_seconds=%.3f error_type=%s",
                operation_name,
                sandbox_id,
                attempt,
                max_attempts,
                delay,
                type(error).__name__,
            )
            if delay > 0:
                await asyncio.sleep(delay)
    raise AssertionError("unreachable")


class E2BSandboxState(str, Enum):
    """Serialized application view of one E2B sandbox lifecycle."""

    RUNNING = "running"
    PAUSING = "pausing"
    PAUSE_UNKNOWN = "pause_unknown"
    PAUSED = "paused"
    RESUMING = "resuming"
    CLOSING = "closing"
    CLOSED = "closed"


class E2BSandboxFactory:
    """Create one internet-disabled E2B Cloud sandbox for an agent turn."""

    def __init__(
        self,
        *,
        api_key: str,
        template: str,
        turn_timeout_seconds: float,
        command_timeout_seconds: float,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        pause_request_timeout_seconds: float = 5.0,
        control_request_timeout_seconds: float = 2.0,
        reaper_interval_seconds: float = 30.0,
        cleanup_manager: E2BSandboxCleanupManager | None = None,
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
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        if pause_request_timeout_seconds <= 0:
            raise ValueError("pause_request_timeout_seconds must be positive")
        if control_request_timeout_seconds <= 0:
            raise ValueError("control_request_timeout_seconds must be positive")
        if reaper_interval_seconds <= 0:
            raise ValueError("reaper_interval_seconds must be positive")
        self._api_key = api_key
        self._template = template
        self._turn_timeout_seconds = turn_timeout_seconds
        self._command_timeout_seconds = command_timeout_seconds
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._pause_request_timeout_seconds = pause_request_timeout_seconds
        self._control_request_timeout_seconds = control_request_timeout_seconds
        self._cleanup_manager = cleanup_manager or E2BSandboxCleanupManager(
            api_key=api_key,
            request_timeout_seconds=control_request_timeout_seconds,
            retry_backoff_seconds=retry_backoff_seconds,
            reaper_interval_seconds=reaper_interval_seconds,
        )
        self._create_sandbox = create_sandbox or AsyncSandbox.create

    @classmethod
    def from_settings(cls, settings: AiSettings) -> "E2BSandboxFactory":
        """Create a factory from validated application settings."""
        return cls(
            api_key=settings.e2b_api_key,
            template=settings.e2b_template,
            turn_timeout_seconds=settings.sandbox_turn_timeout_seconds,
            command_timeout_seconds=settings.sandbox_command_timeout_seconds,
            max_attempts=settings.sandbox_max_attempts,
            retry_backoff_seconds=settings.sandbox_retry_backoff_seconds,
            pause_request_timeout_seconds=settings.sandbox_pause_request_timeout_seconds,
            control_request_timeout_seconds=settings.sandbox_control_request_timeout_seconds,
            reaper_interval_seconds=settings.sandbox_reaper_interval_seconds,
        )

    async def start_cleanup(self) -> None:
        """Start startup and periodic stale-sandbox reconciliation."""
        await self._cleanup_manager.start()

    async def stop_cleanup(self) -> None:
        """Stop this process's cleanup worker."""
        await self._cleanup_manager.stop()

    async def create(self) -> "E2BSandboxBackend":
        started = time.monotonic()
        creation = asyncio.create_task(
            self._create_sandbox(
                template=self._template,
                timeout=math.ceil(self._turn_timeout_seconds),
                secure=True,
                allow_internet_access=False,
                metadata=self._cleanup_manager.metadata_for_turn(self._turn_timeout_seconds),
                lifecycle={
                    # Retain memory because filesystem-only snapshots cold-boot on resume.
                    "on_timeout": {"action": "pause", "keep_memory": True},
                    "auto_resume": True,
                },
                api_key=self._api_key,
            )
        )
        try:
            sandbox = await asyncio.shield(creation)
        except asyncio.CancelledError:
            await self._destroy_after_cancelled_creation(creation)
            raise
        except Exception as exc:
            raise SandboxError("E2B could not create a sandbox.") from exc
        backend = E2BSandboxBackend(
            sandbox,
            command_timeout_seconds=self._command_timeout_seconds,
            max_attempts=self._max_attempts,
            retry_backoff_seconds=self._retry_backoff_seconds,
            pause_request_timeout_seconds=self._pause_request_timeout_seconds,
            control_request_timeout_seconds=self._control_request_timeout_seconds,
            defer_cleanup=self._cleanup_manager.defer,
            confirm_cleanup=self._cleanup_manager.confirm,
        )
        logger.info(
            "sandbox created sandbox_id=%s provider=e2b latency_seconds=%.3f",
            backend.sandbox_id,
            time.monotonic() - started,
        )
        return backend

    async def _destroy_after_cancelled_creation(self, creation: asyncio.Task[Any]) -> None:
        """Finish an in-flight create request so its sandbox can be killed."""
        try:
            sandbox = await asyncio.shield(creation)
        except BaseException:
            logger.exception("cancelled sandbox creation did not return a sandbox")
            return
        try:
            await asyncio.shield(
                _retry_e2b_request(
                    lambda: sandbox.kill(request_timeout=self._control_request_timeout_seconds),
                    operation_name="kill_after_cancelled_create",
                    sandbox_id=str(sandbox.sandbox_id),
                    max_attempts=self._max_attempts,
                    backoff_seconds=self._retry_backoff_seconds,
                )
            )
        except BaseException:
            self._cleanup_manager.defer(str(sandbox.sandbox_id))
            logger.exception(
                "sandbox cleanup failed after creation cancellation sandbox_id=%s",
                sandbox.sandbox_id,
            )
        else:
            logger.info(
                "sandbox destroyed after creation cancellation sandbox_id=%s provider=e2b",
                sandbox.sandbox_id,
            )


class E2BSandboxBackend:
    """Expose raw E2B file, command, and lifecycle operations."""

    def __init__(
        self,
        sandbox: Any,
        *,
        command_timeout_seconds: float,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        pause_request_timeout_seconds: float = 5.0,
        control_request_timeout_seconds: float = 2.0,
        defer_cleanup: Callable[[str], None] | None = None,
        confirm_cleanup: Callable[[str], None] | None = None,
    ) -> None:
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        if pause_request_timeout_seconds <= 0:
            raise ValueError("pause_request_timeout_seconds must be positive")
        if control_request_timeout_seconds <= 0:
            raise ValueError("control_request_timeout_seconds must be positive")
        self._sandbox = sandbox
        self._command_timeout_seconds = command_timeout_seconds
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._pause_request_timeout_seconds = pause_request_timeout_seconds
        self._control_request_timeout_seconds = control_request_timeout_seconds
        self._defer_cleanup = defer_cleanup
        self._confirm_cleanup = confirm_cleanup
        self._state = E2BSandboxState.RUNNING
        self._close_started = False
        self._lifecycle_lock = asyncio.Lock()
        self._pause_task: asyncio.Task[None] | None = None
        self._activity_cancelled_pause_task: asyncio.Task[None] | None = None
        self._paused_at: float | None = None
        self._commands = 0
        self._created_at = time.monotonic()
        self._execution_seconds = 0.0
        self._pause_count = 0
        self._pause_cancel_count = 0
        self._pause_transition_seconds = 0.0
        self._resume_count = 0
        self._resume_wait_seconds = 0.0
        self._max_resume_wait_seconds = 0.0
        self._suspended_seconds = 0.0
        self._teardown_seconds = 0.0

    @property
    def sandbox_id(self) -> str:
        return str(self._sandbox.sandbox_id)

    @property
    def lifecycle_state(self) -> E2BSandboxState:
        """Expose the current transition state for telemetry and tests."""
        return self._state

    @property
    def lifecycle_metrics(self) -> SandboxLifecycleMetrics:
        """Snapshot provider lifecycle costs without expanding SandboxBackend."""
        suspended_seconds = self._suspended_seconds
        if self._paused_at is not None:
            suspended_seconds += time.monotonic() - self._paused_at
        return SandboxLifecycleMetrics(
            execution_seconds=self._execution_seconds,
            pause_count=self._pause_count,
            pause_cancel_count=self._pause_cancel_count,
            pause_transition_seconds=self._pause_transition_seconds,
            resume_count=self._resume_count,
            resume_wait_seconds=self._resume_wait_seconds,
            max_resume_wait_seconds=self._max_resume_wait_seconds,
            suspended_seconds=suspended_seconds,
            teardown_seconds=self._teardown_seconds,
        )

    async def write_file(self, path: str, content: str | bytes) -> None:
        async with self._active_operation():
            started = time.monotonic()
            try:
                await self._request_with_retry(
                    "write_file",
                    lambda: self._sandbox.files.write(path, content, user=E2B_USER),
                )
            except Exception as exc:
                raise SandboxError(f"E2B could not write sandbox file: {path}") from exc
            finally:
                self._execution_seconds += time.monotonic() - started

    async def read_file(self, path: str) -> bytes:
        async with self._active_operation():
            started = time.monotonic()
            try:
                content = await self._request_with_retry(
                    "read_file",
                    lambda: self._sandbox.files.read(path, format="bytes", user=E2B_USER),
                )
            except FileNotFoundException as exc:
                raise SandboxFileNotFoundError(f"Sandbox file not found: {path}") from exc
            except Exception as exc:
                raise SandboxError(f"E2B could not read sandbox file: {path}") from exc
            finally:
                self._execution_seconds += time.monotonic() - started
        return bytes(content)

    async def run(self, command: str, *, timeout_seconds: float | None = None) -> CommandResult:
        timeout = timeout_seconds if timeout_seconds is not None else self._command_timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout_seconds must be positive")

        async with self._active_operation():
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
                duration = time.monotonic() - started
                self._execution_seconds += duration
                destroyed = await self._destroy_locked()
                logger.warning(
                    "sandbox command timed out sandbox_id=%s command_number=%s duration_seconds=%.3f destroyed=%s",
                    self.sandbox_id,
                    self._commands,
                    duration,
                    destroyed,
                )
                return CommandResult(
                    "",
                    "",
                    COMMAND_TIMEOUT_EXIT_CODE,
                    duration_seconds=duration,
                    timed_out=True,
                )
            except Exception as exc:
                self._execution_seconds += time.monotonic() - started
                raise SandboxError("E2B could not run the sandbox command.") from exc

            duration = time.monotonic() - started
            self._execution_seconds += duration
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
        if self._state is E2BSandboxState.CLOSED:
            return
        self._close_started = True
        self._cancel_pending_pause()
        try:
            async with self._lifecycle_lock:
                if self._state is E2BSandboxState.CLOSED:
                    return
                if not await self._destroy_locked():
                    raise SandboxError(f"E2B could not destroy sandbox {self.sandbox_id}.")
                if self._confirm_cleanup is not None:
                    self._confirm_cleanup(self.sandbox_id)
        except BaseException:
            if self._defer_cleanup is not None:
                self._defer_cleanup(self.sandbox_id)
            raise

    @asynccontextmanager
    async def _active_operation(self) -> AsyncIterator[None]:
        """Serialize one operation with pause, resume, and close transitions."""
        self._cancel_pending_pause(for_activity=True)
        async with self._lifecycle_lock:
            self._cancel_pending_pause_locked()
            self._ensure_open()
            await self._resume_locked()
            try:
                yield
            finally:
                if self._state not in {E2BSandboxState.CLOSING, E2BSandboxState.CLOSED}:
                    self._schedule_pause_locked()

    def _schedule_pause_locked(self) -> None:
        if self._close_started or self._state is not E2BSandboxState.RUNNING:
            return
        self._cancel_pending_pause_locked()
        self._pause_task = asyncio.create_task(self._pause_when_idle())

    async def _pause_when_idle(self) -> None:
        """Explicitly warm-pause unless another operation arrives first."""
        current_task = asyncio.current_task()
        try:
            # Cleanup runs in a separate cancellation-shielded task. Yield once so
            # it can mark the sandbox as closing and cancel this terminal pause
            # before the request reaches E2B.
            await asyncio.sleep(0)
            async with self._lifecycle_lock:
                if (
                    self._close_started
                    or self._state is not E2BSandboxState.RUNNING
                    or self._pause_task is not current_task
                ):
                    return
                self._state = E2BSandboxState.PAUSING
                started = time.monotonic()
                try:
                    async with asyncio.timeout(self._pause_request_timeout_seconds):
                        await self._sandbox.pause(
                            keep_memory=True,
                            request_timeout=self._pause_request_timeout_seconds,
                        )
                except asyncio.CancelledError:
                    self._state = E2BSandboxState.RUNNING
                    raise
                except TimeoutError:
                    self._pause_transition_seconds += time.monotonic() - started
                    # The control plane may have accepted pause even though its
                    # response missed our deadline. Probe auto-resume before the
                    # next operation instead of treating the sandbox as running.
                    self._state = E2BSandboxState.PAUSE_UNKNOWN
                    logger.warning(
                        "sandbox pause timed out sandbox_id=%s timeout_seconds=%.3f outcome=unknown",
                        self.sandbox_id,
                        self._pause_request_timeout_seconds,
                    )
                    return
                except Exception:
                    self._state = E2BSandboxState.RUNNING
                    logger.exception("sandbox pause failed sandbox_id=%s", self.sandbox_id)
                    return
                now = time.monotonic()
                latency = now - started
                self._pause_count += 1
                self._pause_transition_seconds += latency
                self._paused_at = now
                self._state = E2BSandboxState.PAUSED
                logger.info(
                    "sandbox paused sandbox_id=%s pause_count=%s pause_transition_seconds=%.3f",
                    self.sandbox_id,
                    self._pause_count,
                    latency,
                )
        finally:
            if self._activity_cancelled_pause_task is current_task:
                self._activity_cancelled_pause_task = None
            if self._pause_task is current_task:
                self._pause_task = None

    async def _resume_locked(self) -> None:
        previous_state = self._state
        if previous_state not in {E2BSandboxState.PAUSED, E2BSandboxState.PAUSE_UNKNOWN}:
            return
        self._state = E2BSandboxState.RESUMING
        started = time.monotonic()
        try:
            # This filesystem request exercises E2B auto-resume without an explicit connect call.
            async def resume_probe() -> bool:
                async with asyncio.timeout(self._control_request_timeout_seconds):
                    return await self._sandbox.files.exists(E2B_WORKSPACE, user=E2B_USER)

            await self._request_with_retry(
                "resume",
                resume_probe,
            )
        except Exception as exc:
            self._state = previous_state
            raise SandboxError(f"E2B could not resume sandbox {self.sandbox_id}.") from exc

        now = time.monotonic()
        latency = now - started
        self._resume_count += 1
        self._resume_wait_seconds += latency
        self._max_resume_wait_seconds = max(self._max_resume_wait_seconds, latency)
        if self._paused_at is not None:
            self._suspended_seconds += started - self._paused_at
            self._paused_at = None
        self._state = E2BSandboxState.RUNNING
        logger.info(
            "sandbox resumed sandbox_id=%s resume_count=%s resume_wait_seconds=%.3f suspended_seconds=%.3f",
            self.sandbox_id,
            self._resume_count,
            latency,
            self._suspended_seconds,
        )

    async def _destroy_locked(self) -> bool:
        self._close_started = True
        self._cancel_pending_pause_locked()
        previous_state = self._state
        self._state = E2BSandboxState.CLOSING
        started = time.monotonic()
        try:
            await self._request_with_retry(
                "kill",
                lambda: self._sandbox.kill(request_timeout=self._control_request_timeout_seconds),
            )
        except SandboxNotFoundException:
            pass
        except Exception:
            self._state = previous_state
            logger.exception("sandbox cleanup failed sandbox_id=%s", self.sandbox_id)
            return False

        now = time.monotonic()
        teardown_seconds = now - started
        self._teardown_seconds += teardown_seconds
        if self._paused_at is not None:
            self._suspended_seconds += started - self._paused_at
            self._paused_at = None
        self._state = E2BSandboxState.CLOSED
        logger.info(
            "sandbox destroyed sandbox_id=%s provider=e2b commands=%s pause_count=%s pause_cancel_count=%s "
            "pause_transition_seconds=%.3f resume_wait_seconds=%.3f suspended_seconds=%.3f "
            "teardown_seconds=%.3f lifetime_seconds=%.3f",
            self.sandbox_id,
            self._commands,
            self._pause_count,
            self._pause_cancel_count,
            self._pause_transition_seconds,
            self._resume_wait_seconds,
            self._suspended_seconds,
            teardown_seconds,
            now - self._created_at,
        )
        return True

    async def _request_with_retry(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[RequestResult]],
    ) -> RequestResult:
        return await _retry_e2b_request(
            operation,
            operation_name=operation_name,
            sandbox_id=self.sandbox_id,
            max_attempts=self._max_attempts,
            backoff_seconds=self._retry_backoff_seconds,
        )

    def _cancel_pending_pause(self, *, for_activity: bool = False) -> None:
        task = self._pause_task
        if (
            for_activity
            and self._state is E2BSandboxState.PAUSING
            and task is not None
            and not task.done()
            and task is not self._activity_cancelled_pause_task
        ):
            self._activity_cancelled_pause_task = task
            self._pause_cancel_count += 1
            logger.info(
                "sandbox pause cancelled by activity sandbox_id=%s pause_cancel_count=%s",
                self.sandbox_id,
                self._pause_cancel_count,
            )
        self._cancel_pending_pause_locked()

    def _cancel_pending_pause_locked(self) -> None:
        task = self._pause_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        self._pause_task = None

    def _ensure_open(self) -> None:
        if self._close_started or self._state in {E2BSandboxState.CLOSING, E2BSandboxState.CLOSED}:
            raise SandboxError(f"E2B sandbox {self.sandbox_id} is closed")
