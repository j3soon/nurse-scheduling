"""Reap overdue Nurse Scheduling E2B sandboxes once."""

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
import os
from collections.abc import Callable

from ...sentry import init_sentry
from .e2b_cleanup import E2BSandboxCleanupManager

logger = logging.getLogger("nurse_scheduling.ai.sandbox.reap")


def _positive_float_from_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _non_negative_float_from_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


async def reap_once(
    *,
    manager_factory: Callable[..., E2BSandboxCleanupManager] = E2BSandboxCleanupManager,
) -> int:
    """Delete currently overdue sandboxes and report whether cleanup completed."""
    api_key = os.getenv("E2B_API_KEY", "").strip()
    if not api_key:
        raise ValueError("E2B_API_KEY is required")

    manager = manager_factory(
        api_key=api_key,
        request_timeout_seconds=_positive_float_from_env("AI_SANDBOX_CONTROL_REQUEST_TIMEOUT_SECONDS", 2.0),
        retry_backoff_seconds=_non_negative_float_from_env("AI_SANDBOX_RETRY_BACKOFF_SECONDS", 0.5),
        reaper_interval_seconds=_positive_float_from_env("AI_SANDBOX_REAPER_INTERVAL_SECONDS", 30.0),
    )
    reconciliation_succeeded = await manager.reconcile_once()
    await manager.retry_deferred_once()
    if not reconciliation_succeeded or manager.pending_count:
        logger.error(
            "E2B sandbox reaper incomplete reconciliation_succeeded=%s pending_count=%s",
            reconciliation_succeeded,
            manager.pending_count,
            extra={
                "reconciliation_succeeded": reconciliation_succeeded,
                "pending_count": manager.pending_count,
            },
        )
        return 1
    logger.info("E2B sandbox reaper completed pending_count=0")
    return 0


def main() -> int:
    """Run one cleanup pass for use by cron or a platform scheduler."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_sentry(os.getenv("APP_VERSION", "e2b-reaper"), app="ai-backend")
    try:
        return asyncio.run(reap_once())
    except ValueError as error:
        logger.error("E2B sandbox reaper configuration invalid error=%s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
