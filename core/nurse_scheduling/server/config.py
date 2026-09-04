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
from datetime import datetime, timezone

from ..scheduler import ORTOOLS_CP_SAT_SOLVER
from .auth import (
    AUTH_REQUIRED_ENV_NAME,
    AUTH_TOKEN_ENV_NAME,
    RECOMMENDED_AUTH_TOKEN_LENGTH,
    STREAM_TOKEN_GRACE_SECONDS,
    normalize_auth_token,
)
from .solver_options import normalize_solver_option

DEFAULT_MAX_RETAINED_JOBS = 128
"""Default maximum number of jobs retained across all lifecycle states."""
DEFAULT_JOB_RETENTION_SECONDS = 24 * 60 * 60
"""Default 24-hour retention period for terminal jobs."""
DEFAULT_MAX_EVENTS_PER_JOB = 1_000
"""Default maximum number of replayable events retained for one job."""
DEFAULT_TIMEOUT_GRACE_SECONDS = 90.0
"""Default grace period before forcibly terminating a timed-out solver."""
CLAIMED_PERFORMANCE_ENV_NAMES = (
    "CLAIMED_PERFORMANCE_SCORE",
    "CLAIMED_PERFORMANCE_APP_VERSION",
    "CLAIMED_PERFORMANCE_MEASURED_AT",
)
"""Environment settings that form one atomic self-claimed benchmark result."""
DEFAULT_USAGE_METRICS_RETENTION_DAYS = 30
"""Default retention period for minimal job telemetry."""
MIN_USAGE_METRICS_RETENTION_DAYS = 9
"""Shortest retention that covers a complete local week before reporting."""


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


def _boolean(name: str, default: bool) -> bool:
    """Read a boolean environment setting."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _solver_ids(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Read a comma-separated solver allowlist."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    values = tuple(value.strip() for value in raw_value.split(",") if value.strip())
    if not values:
        raise ValueError(f"{name} must contain at least one solver")
    return values


@dataclass(frozen=True)
class ClaimedPerformance:
    """Self-reported normalized benchmark score for one server."""

    score: float
    """Normalized benchmark score where 100 is the reference performance."""
    app_version: str
    """Application version benchmarked to produce the score."""
    measured_at: datetime
    """Timezone-aware time when the benchmark report was created."""

    def __post_init__(self) -> None:
        """Validate and normalize directly constructed benchmark metadata."""
        if not math.isfinite(self.score) or self.score <= 0:
            raise ValueError("claimed performance score must be positive")
        app_version = self.app_version.strip()
        if not app_version:
            raise ValueError("claimed performance app version must not be empty")
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("claimed performance measured time must include a timezone")
        object.__setattr__(self, "app_version", app_version)
        object.__setattr__(self, "measured_at", self.measured_at.astimezone(timezone.utc))


def _claimed_performance() -> ClaimedPerformance | None:
    """Read an optional complete claimed-performance result from the environment."""
    values = {name: (os.getenv(name) or "").strip() for name in CLAIMED_PERFORMANCE_ENV_NAMES}
    configured_names = {name for name, value in values.items() if value}
    if not configured_names:
        return None
    if len(configured_names) != len(CLAIMED_PERFORMANCE_ENV_NAMES):
        raise ValueError(f"{', '.join(CLAIMED_PERFORMANCE_ENV_NAMES)} must be set together")
    try:
        score = float(values["CLAIMED_PERFORMANCE_SCORE"])
    except ValueError as error:
        raise ValueError("CLAIMED_PERFORMANCE_SCORE must be a positive number") from error
    if not math.isfinite(score) or score <= 0:
        raise ValueError("CLAIMED_PERFORMANCE_SCORE must be a positive number")
    try:
        measured_at = datetime.fromisoformat(values["CLAIMED_PERFORMANCE_MEASURED_AT"])
    except ValueError as error:
        raise ValueError("CLAIMED_PERFORMANCE_MEASURED_AT must be an ISO 8601 date and time") from error
    try:
        return ClaimedPerformance(
            score=score,
            app_version=values["CLAIMED_PERFORMANCE_APP_VERSION"],
            measured_at=measured_at,
        )
    except ValueError as error:
        raise ValueError(f"Invalid claimed performance configuration: {error}") from error


@dataclass(frozen=True)
class ServerSettings:
    """All configuration required to construct one server process."""

    job_backend: str = "memory"
    """Persistence backend selected for this process: `memory` or `redis`."""
    redis_url: str = "redis://localhost:6379/0"
    """Connection URL used by the Redis job store."""
    redis_key_prefix: str = "nurse_scheduling:jobs:v0"
    """Namespace and schema version prepended to every Redis key."""
    max_pending_jobs: int = 32
    """Maximum number of queued, running, or cancelling jobs."""
    max_retained_jobs: int = DEFAULT_MAX_RETAINED_JOBS
    """Maximum total jobs retained, including terminal history."""
    job_retention_seconds: int = DEFAULT_JOB_RETENTION_SECONDS
    """Time terminal jobs remain available before maintenance deletes them."""
    max_events_per_job: int = DEFAULT_MAX_EVENTS_PER_JOB
    """Maximum replayable events retained for each job."""
    claim_poll_seconds: float = 1.0
    """Worker delay between attempts to claim a queued job."""
    worker_lease_seconds: float = 90.0
    """Time a worker remains online without renewing its shared lease."""
    maintenance_interval_seconds: float = 30.0
    """Delay between worker-expiry and retention maintenance passes."""
    sse_keepalive_seconds: float = 10.0
    """Maximum SSE wait before emitting a keepalive comment."""
    max_yaml_bytes: int = 2 * 1024 * 1024
    """Largest accepted YAML request body in bytes."""
    solver_ids: tuple[str, ...] = (ORTOOLS_CP_SAT_SOLVER,)
    """Ordered solver allowlist advertised and accepted by this deployment."""
    default_solver: str = ORTOOLS_CP_SAT_SOLVER
    """Solver used when an optimization request omits the solver field."""
    min_timeout_seconds: int = 1
    """Smallest optimization timeout accepted from a request."""
    default_timeout_seconds: int = 5 * 60
    """Optimization timeout used when the request omits one."""
    max_timeout_seconds: int = 60 * 60
    """Largest optimization timeout accepted from a request."""
    default_prettify: bool = True
    """Schedule-prettification setting used when a request omits one."""
    timeout_grace_seconds: float = DEFAULT_TIMEOUT_GRACE_SECONDS
    """Time allowed for a solver to return after its requested timeout."""
    claimed_performance: ClaimedPerformance | None = None
    """Optional self-reported benchmark score and its provenance."""
    auth_token: str | None = None
    """Shared token required by protected routes, `None` to serve without authentication."""
    auth_required: bool = False
    """Whether this deployment must authenticate, which makes a missing token a startup failure."""
    usage_metrics_enabled: bool = False
    """Whether Redis records minimal per-job backend telemetry."""
    usage_metrics_key_prefix: str = "nurse_scheduling:usage:v0"
    """Namespace and schema version prepended to telemetry keys."""
    usage_metrics_retention_days: int = DEFAULT_USAGE_METRICS_RETENTION_DAYS
    """Retention period for every telemetry row."""

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
            "min_timeout_seconds",
            "default_timeout_seconds",
            "max_timeout_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.usage_metrics_retention_days < MIN_USAGE_METRICS_RETENTION_DAYS:
            raise ValueError(f"usage_metrics_retention_days must be at least {MIN_USAGE_METRICS_RETENTION_DAYS}")
        for name in (
            "claim_poll_seconds",
            "worker_lease_seconds",
            "maintenance_interval_seconds",
            "sse_keepalive_seconds",
            "timeout_grace_seconds",
        ):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_retained_jobs < self.max_pending_jobs:
            raise ValueError("max_retained_jobs must be at least max_pending_jobs")
        if self.min_timeout_seconds > self.default_timeout_seconds:
            raise ValueError("min_timeout_seconds must not exceed default_timeout_seconds")
        if self.default_timeout_seconds > self.max_timeout_seconds:
            raise ValueError("default_timeout_seconds must not exceed max_timeout_seconds")
        if isinstance(self.solver_ids, str) or not self.solver_ids:
            raise ValueError("solver_ids must contain at least one solver")
        normalized_solver_ids = tuple(normalize_solver_option(value) for value in self.solver_ids)
        if len(set(normalized_solver_ids)) != len(normalized_solver_ids):
            raise ValueError("solver_ids must not contain duplicates")
        normalized_default_solver = normalize_solver_option(self.default_solver)
        if normalized_default_solver not in normalized_solver_ids:
            raise ValueError("default_solver must be included in solver_ids")
        if not isinstance(self.default_prettify, bool):
            raise TypeError("default_prettify must be a boolean")
        object.__setattr__(self, "solver_ids", normalized_solver_ids)
        object.__setattr__(self, "default_solver", normalized_default_solver)
        object.__setattr__(
            self,
            "auth_token",
            normalize_auth_token(self.auth_token, warn_on_short=not self.auth_required),
        )
        # Images built for deployment set this, so an unauthenticated public server stays a
        # deliberate choice rather than the result of a forgotten token.
        if self.auth_required and self.auth_token is None:
            raise ValueError(f"{AUTH_REQUIRED_ENV_NAME} is set, so {AUTH_TOKEN_ENV_NAME} must not be empty")
        if self.auth_required and len(self.auth_token) < RECOMMENDED_AUTH_TOKEN_LENGTH:
            raise ValueError(
                f"{AUTH_REQUIRED_ENV_NAME} is set, so {AUTH_TOKEN_ENV_NAME} must be at least "
                f"{RECOMMENDED_AUTH_TOKEN_LENGTH} characters"
            )

        if self.usage_metrics_enabled and self.job_backend != "redis":
            raise ValueError("USAGE_METRICS_ENABLED requires JOB_BACKEND=redis")
        if self.usage_metrics_enabled and not self.usage_metrics_key_prefix.strip().rstrip(":"):
            raise ValueError("USAGE_METRICS_KEY_PREFIX must not be empty")
        if self.usage_metrics_enabled and self.usage_metrics_key_prefix.rstrip(":") == self.redis_key_prefix.rstrip(
            ":"
        ):
            raise ValueError("USAGE_METRICS_KEY_PREFIX must differ from JOB_REDIS_KEY_PREFIX")

    @property
    def stream_token_ttl_seconds(self) -> int:
        """Lifetime of an event-stream token.

        A stream stays open for at most one full optimization plus the grace period before a
        timed-out solver is terminated, so the token outlives every legitimate stream while
        still expiring soon after the longest run this deployment allows.
        """
        return self.max_timeout_seconds + math.ceil(self.timeout_grace_seconds) + STREAM_TOKEN_GRACE_SECONDS

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Load and validate settings once at application construction.

        Raises:
            ValueError: If an environment value is invalid or inconsistent.
        """
        job_backend = os.getenv("JOB_BACKEND", "memory").strip().lower()
        return cls(
            job_backend=job_backend,
            redis_url=os.getenv("JOB_REDIS_URL", "redis://localhost:6379/0"),
            redis_key_prefix=os.getenv("JOB_REDIS_KEY_PREFIX", "nurse_scheduling:jobs:v0"),
            max_pending_jobs=_positive_int("JOB_MAX_PENDING", 32),
            max_retained_jobs=_positive_int("JOB_MAX_RETAINED", DEFAULT_MAX_RETAINED_JOBS),
            job_retention_seconds=_positive_int("JOB_RETENTION_SECONDS", DEFAULT_JOB_RETENTION_SECONDS),
            max_events_per_job=_positive_int("JOB_MAX_EVENTS_PER_JOB", DEFAULT_MAX_EVENTS_PER_JOB),
            claim_poll_seconds=_positive_float("JOB_CLAIM_POLL_SECONDS", 1.0),
            worker_lease_seconds=_positive_float("JOB_WORKER_LEASE_SECONDS", 90.0),
            maintenance_interval_seconds=_positive_float("JOB_MAINTENANCE_INTERVAL_SECONDS", 30.0),
            sse_keepalive_seconds=_positive_float("JOB_SSE_KEEPALIVE_SECONDS", 10.0),
            max_yaml_bytes=_positive_int("OPTIMIZE_MAX_YAML_BYTES", 2 * 1024 * 1024),
            solver_ids=_solver_ids("OPTIMIZE_SOLVERS", (ORTOOLS_CP_SAT_SOLVER,)),
            default_solver=os.getenv("OPTIMIZE_DEFAULT_SOLVER", ORTOOLS_CP_SAT_SOLVER),
            min_timeout_seconds=_positive_int("OPTIMIZE_MIN_TIMEOUT_SECONDS", 1),
            default_timeout_seconds=_positive_int("OPTIMIZE_DEFAULT_TIMEOUT_SECONDS", 5 * 60),
            max_timeout_seconds=_positive_int("OPTIMIZE_MAX_TIMEOUT_SECONDS", 60 * 60),
            default_prettify=_boolean("OPTIMIZE_DEFAULT_PRETTIFY", True),
            timeout_grace_seconds=_positive_float(
                "OPTIMIZE_TIMEOUT_GRACE_SECONDS",
                DEFAULT_TIMEOUT_GRACE_SECONDS,
            ),
            claimed_performance=_claimed_performance(),
            auth_token=os.getenv(AUTH_TOKEN_ENV_NAME),
            auth_required=_boolean(AUTH_REQUIRED_ENV_NAME, False),
            usage_metrics_enabled=_boolean("USAGE_METRICS_ENABLED", False),
            usage_metrics_key_prefix=os.getenv(
                "USAGE_METRICS_KEY_PREFIX",
                "nurse_scheduling:usage:v0",
            ),
            usage_metrics_retention_days=_positive_int(
                "USAGE_METRICS_RETENTION_DAYS",
                DEFAULT_USAGE_METRICS_RETENTION_DAYS,
            ),
        )
