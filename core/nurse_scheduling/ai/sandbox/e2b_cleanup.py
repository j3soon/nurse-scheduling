"""Deferred and stale-sandbox cleanup for E2B Cloud."""

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
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from e2b import AsyncSandbox
from e2b.api.client.models.sandbox_state import SandboxState
from e2b.exceptions import SandboxException, SandboxNotFoundException
from e2b.sandbox.sandbox_api import SandboxQuery

logger = logging.getLogger("nurse_scheduling.ai.sandbox.e2b_cleanup")
MANAGED_METADATA_KEY = "nurse_scheduling_ai_managed"
MANAGED_METADATA_VALUE = "true"
HARD_DEADLINE_METADATA_KEY = "nurse_scheduling_ai_hard_deadline"
MAX_CLEANUP_BACKOFF_SECONDS = 60.0

ListSandboxes = Callable[..., Any]
KillSandbox = Callable[..., Awaitable[bool]]


@dataclass
class _DeferredCleanup:
    """Retry state for one sandbox whose deletion was not confirmed."""

    attempts: int = 0
    next_attempt_at: float = 0.0
    failure_escalated: bool = False


class E2BSandboxCleanupManager:
    """Reap owned E2B sandboxes until deletion is confirmed."""

    def __init__(
        self,
        *,
        api_key: str,
        request_timeout_seconds: float,
        retry_backoff_seconds: float,
        reaper_interval_seconds: float,
        list_sandboxes: ListSandboxes | None = None,
        kill_sandbox: KillSandbox | None = None,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        if reaper_interval_seconds <= 0:
            raise ValueError("reaper_interval_seconds must be positive")
        self._api_key = api_key
        self._request_timeout_seconds = request_timeout_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
        self._reaper_interval_seconds = reaper_interval_seconds
        self._list_sandboxes = list_sandboxes or AsyncSandbox.list
        self._kill_sandbox = kill_sandbox or AsyncSandbox.kill
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self._pending: dict[str, _DeferredCleanup] = {}
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def pending_count(self) -> int:
        """Return the number of deletions awaiting confirmation."""
        return len(self._pending)

    def metadata_for_turn(self, turn_timeout_seconds: float) -> dict[str, str]:
        """Tag a sandbox so a later process can enforce its hard deadline."""
        return {
            MANAGED_METADATA_KEY: MANAGED_METADATA_VALUE,
            HARD_DEADLINE_METADATA_KEY: str(self._wall_clock() + turn_timeout_seconds),
        }

    async def start(self) -> None:
        """Start startup reconciliation and periodic cleanup."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="e2b-sandbox-reaper")
        await asyncio.sleep(0)

    async def stop(self) -> None:
        """Stop the local worker. Metadata preserves work for the next process."""
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def defer(self, sandbox_id: str) -> None:
        """Queue an unconfirmed deletion without extending the user request."""
        if sandbox_id not in self._pending:
            self._pending[sandbox_id] = _DeferredCleanup(next_attempt_at=self._monotonic())
            logger.warning(
                "sandbox deletion unconfirmed, background cleanup queued sandbox_id=%s",
                sandbox_id,
                extra={"sandbox_id": sandbox_id},
            )
        self._wake.set()

    async def reconcile_once(self) -> None:
        """Find owned running or paused sandboxes beyond their hard deadline."""
        try:
            paginator = self._list_sandboxes(
                query=SandboxQuery(
                    metadata={MANAGED_METADATA_KEY: MANAGED_METADATA_VALUE},
                    state=[SandboxState.RUNNING, SandboxState.PAUSED],
                ),
                limit=100,
                api_key=self._api_key,
                request_timeout=self._request_timeout_seconds,
            )
            while paginator.has_next:
                for sandbox in await paginator.next_items():
                    deadline = _parse_deadline(sandbox.metadata.get(HARD_DEADLINE_METADATA_KEY))
                    if deadline is not None and deadline <= self._wall_clock():
                        sandbox_id = str(sandbox.sandbox_id)
                        if sandbox_id in self._pending:
                            continue
                        overdue_seconds = self._wall_clock() - deadline
                        state = str(getattr(sandbox, "state", "unknown"))
                        logger.error(
                            "overdue sandbox discovered sandbox_id=%s state=%s overdue_seconds=%.3f",
                            sandbox_id,
                            state,
                            overdue_seconds,
                            extra={
                                "sandbox_id": sandbox_id,
                                "sandbox_state": state,
                                "overdue_seconds": overdue_seconds,
                            },
                        )
                        self.defer(sandbox_id)
        except asyncio.CancelledError:
            raise
        except (SandboxException, TimeoutError):
            logger.exception("stale sandbox reconciliation failed")

    async def retry_deferred_once(self) -> None:
        """Try every due deletion once and retain failures with capped backoff."""
        now = self._monotonic()
        for sandbox_id, cleanup in tuple(self._pending.items()):
            if cleanup.next_attempt_at > now:
                continue
            try:
                killed = await self._kill_sandbox(
                    sandbox_id,
                    api_key=self._api_key,
                    request_timeout=self._request_timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except SandboxNotFoundException:
                killed = False
            except (SandboxException, TimeoutError) as error:
                cleanup.attempts += 1
                exponent = min(cleanup.attempts - 1, 16)
                delay = min(
                    max(self._retry_backoff_seconds, 0.1) * (2**exponent),
                    MAX_CLEANUP_BACKOFF_SECONDS,
                )
                cleanup.next_attempt_at = now + delay
                log = logger.warning
                if cleanup.attempts >= 3 and not cleanup.failure_escalated:
                    cleanup.failure_escalated = True
                    log = logger.error
                log(
                    "deferred sandbox cleanup failed sandbox_id=%s attempt=%s retry_in_seconds=%.3f error_type=%s",
                    sandbox_id,
                    cleanup.attempts,
                    delay,
                    type(error).__name__,
                    extra={
                        "sandbox_id": sandbox_id,
                        "cleanup_attempt": cleanup.attempts,
                        "retry_in_seconds": delay,
                        "error_type": type(error).__name__,
                    },
                )
                continue

            self._pending.pop(sandbox_id, None)
            logger.info(
                "deferred sandbox cleanup confirmed sandbox_id=%s outcome=%s",
                sandbox_id,
                "killed" if killed else "already_absent",
                extra={
                    "sandbox_id": sandbox_id,
                    "cleanup_attempts": cleanup.attempts + 1,
                    "cleanup_outcome": "killed" if killed else "already_absent",
                },
            )

    async def _run(self) -> None:
        next_reconciliation = self._monotonic()
        while True:
            now = self._monotonic()
            if now >= next_reconciliation:
                await self.reconcile_once()
                next_reconciliation = self._monotonic() + self._reaper_interval_seconds
            await self.retry_deferred_once()

            now = self._monotonic()
            due_times = [cleanup.next_attempt_at for cleanup in self._pending.values()]
            next_wake = min([next_reconciliation, *due_times])
            delay = max(0.0, next_wake - now)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except TimeoutError:
                pass


def _parse_deadline(value: str | None) -> float | None:
    """Ignore malformed metadata without risking another sandbox's lifecycle."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        logger.warning("sandbox has invalid hard-deadline metadata")
        return None
