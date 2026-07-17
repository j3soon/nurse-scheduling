"""Validated environment-backed configuration for the server application."""

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

import math
import os
from dataclasses import dataclass


DEFAULT_MAX_RETAINED_JOBS = 128
"""Default maximum number of jobs retained across all lifecycle states."""
DEFAULT_JOB_RETENTION_SECONDS = 24 * 60 * 60
"""Default 24-hour retention period for terminal jobs."""
DEFAULT_MAX_EVENTS_PER_JOB = 1_000
"""Default maximum number of replayable events retained for one job."""


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer environment setting.

    Raises:
        ValueError: If the configured value is not a positive integer.
    """
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float(name: str, default: float) -> float:
    """Read a positive floating-point environment setting.

    Raises:
        ValueError: If the configured value is not a positive number.
    """
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


@dataclass(frozen=True)
class ServerSettings:
    """All configuration required to construct one server process."""

    job_backend: str = "memory"
    """Persistence backend selected for this process: `memory` or `redis`."""
    redis_url: str = "redis://localhost:6379/0"
    """Connection URL used by the Redis job store."""
    redis_key_prefix: str = "nurse_scheduling:jobs:v0"
    """Namespace and schema version prepended to every Redis key."""
    max_pending_jobs: int = 8
    """Maximum number of queued, running, or cancelling jobs."""
    max_retained_jobs: int = DEFAULT_MAX_RETAINED_JOBS
    """Maximum total jobs retained, including terminal history."""
    job_retention_seconds: int = DEFAULT_JOB_RETENTION_SECONDS
    """Time terminal jobs remain available before maintenance deletes them."""
    max_events_per_job: int = DEFAULT_MAX_EVENTS_PER_JOB
    """Maximum replayable events retained for each job."""
    claim_poll_seconds: float = 1.0
    """Worker delay between attempts to claim a queued job."""
    claim_lease_seconds: float = 90.0
    """Time a worker claim remains valid without renewal."""
    maintenance_interval_seconds: float = 30.0
    """Delay between claim-expiry and retention maintenance passes."""
    sse_keepalive_seconds: float = 10.0
    """Maximum SSE wait before emitting a keepalive comment."""
    max_yaml_bytes: int = 2 * 1024 * 1024
    """Largest accepted YAML request body in bytes."""
    default_timeout_seconds: int = 5 * 60
    """Optimization timeout used when the request omits one."""
    max_timeout_seconds: int = 60 * 60
    """Largest optimization timeout accepted from a request."""

    def __post_init__(self) -> None:
        """Validate cross-field and direct-construction constraints.

        Raises:
            ValueError: If a setting is unsupported, non-positive, or inconsistent.
        """
        if self.job_backend not in {"memory", "redis"}:
            raise ValueError("JOB_BACKEND must be either 'memory' or 'redis'")
        for name in (
            "max_pending_jobs",
            "max_retained_jobs",
            "job_retention_seconds",
            "max_events_per_job",
            "max_yaml_bytes",
            "default_timeout_seconds",
            "max_timeout_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "claim_poll_seconds",
            "claim_lease_seconds",
            "maintenance_interval_seconds",
            "sse_keepalive_seconds",
        ):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_retained_jobs < self.max_pending_jobs:
            raise ValueError("max_retained_jobs must be at least max_pending_jobs")
        if self.default_timeout_seconds > self.max_timeout_seconds:
            raise ValueError("default_timeout_seconds must not exceed max_timeout_seconds")

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Load and validate settings once at application construction.

        Raises:
            ValueError: If an environment value is invalid or inconsistent.
        """
        return cls(
            job_backend=os.getenv("JOB_BACKEND", "memory").strip().lower(),
            redis_url=os.getenv("JOB_REDIS_URL", "redis://localhost:6379/0"),
            redis_key_prefix=os.getenv("JOB_REDIS_KEY_PREFIX", "nurse_scheduling:jobs:v0"),
            max_pending_jobs=_positive_int("JOB_MAX_PENDING", 8),
            max_retained_jobs=_positive_int("JOB_MAX_RETAINED", DEFAULT_MAX_RETAINED_JOBS),
            job_retention_seconds=_positive_int("JOB_RETENTION_SECONDS", DEFAULT_JOB_RETENTION_SECONDS),
            max_events_per_job=_positive_int("JOB_MAX_EVENTS_PER_JOB", DEFAULT_MAX_EVENTS_PER_JOB),
            claim_poll_seconds=_positive_float("JOB_CLAIM_POLL_SECONDS", 1.0),
            claim_lease_seconds=_positive_float("JOB_CLAIM_LEASE_SECONDS", 90.0),
            maintenance_interval_seconds=_positive_float("JOB_MAINTENANCE_INTERVAL_SECONDS", 30.0),
            sse_keepalive_seconds=_positive_float("JOB_SSE_KEEPALIVE_SECONDS", 10.0),
            max_yaml_bytes=_positive_int("OPTIMIZE_MAX_YAML_BYTES", 2 * 1024 * 1024),
            default_timeout_seconds=_positive_int("OPTIMIZE_DEFAULT_TIMEOUT_SECONDS", 5 * 60),
            max_timeout_seconds=_positive_int("OPTIMIZE_MAX_TIMEOUT_SECONDS", 60 * 60),
        )
