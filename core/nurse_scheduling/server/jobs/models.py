"""Transport-independent models for asynchronous optimization jobs."""

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

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class JobState(str, Enum):
    """Execution lifecycle for an asynchronous job."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        """Return whether no further lifecycle transition is expected."""
        return self in {self.COMPLETED, self.CANCELLED, self.FAILED}


class OptimizationOutcome(str, Enum):
    """Normalized outcome produced by a successful optimization run."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"


@dataclass(frozen=True)
class JobRequest:
    """Normalized inputs controlling one optimization run."""

    input_name: str
    """Original input filename used to derive the artifact filename."""
    client_id: str
    """Opaque client identifier recorded for diagnostics."""
    solver: str
    """Configured scheduling solver identifier."""
    prettify: bool | None
    """Optional schedule-prettification preference."""
    timeout_seconds: int
    """Maximum duration supplied to the scheduling engine."""


@dataclass(frozen=True)
class OptimizationResult:
    """Result of a normally completed optimization run."""

    outcome: OptimizationOutcome
    """Normalized optimization outcome independent of lifecycle state."""
    score: int | None
    """Best objective score, when a schedule was produced."""
    solver_status: str
    """Original status reported by the selected solver."""
    termination_reason: str | None = None
    """Normalized explanation of why solver execution stopped."""


@dataclass(frozen=True)
class JobFailure:
    """Structured failure exposed independently of HTTP."""

    code: str
    """Stable machine-readable failure reason."""
    message: str
    """Human-readable failure explanation."""


@dataclass(frozen=True)
class Job:
    """Persisted metadata and lifecycle state for one job."""

    id: str
    """High-entropy identifier used by clients and persistence."""
    state: JobState
    """Current execution lifecycle state."""
    request: JobRequest
    """Normalized immutable execution inputs."""
    created_at: datetime
    """UTC time at which the job entered the store."""
    revision: int = 0
    """Optimistic-concurrency version incremented by each stored update."""
    started_at: datetime | None = None
    """UTC time at which a worker claimed the job."""
    finished_at: datetime | None = None
    """UTC time at which the job entered a terminal state."""
    worker_id: str | None = None
    """Identity of the worker holding the execution claim."""
    queue_position: int | None = None
    """Derived one-based position while the job is queued."""
    result: OptimizationResult | None = None
    """Normal optimization result populated on completion."""
    failure: JobFailure | None = None
    """Structured reason populated for failed or cancelled jobs."""
    cancel_requested: bool = False
    """Whether cancellation has been requested but may still be in progress."""
    early_completion_requested: bool = False
    """Whether the solver was asked to return its current feasible result."""
    artifact_name: str | None = None
    """Name of the downloadable artifact produced by the job."""


@dataclass(frozen=True)
class JobEvent:
    """Transport-neutral event persisted for a job."""

    type: str
    """Stable event name used by subscribers."""
    data: dict[str, Any]
    """Transport-neutral event payload."""
    occurred_at: datetime
    """UTC time at which the event occurred."""
    id: str | None = None
    """Store-assigned replay cursor, absent before persistence."""


@dataclass(frozen=True)
class StoredArtifact:
    """Named binary result persisted for a job."""

    name: str
    """Filename presented when the artifact is downloaded."""
    media_type: str
    """HTTP media type of the binary content."""
    content: bytes
    """Artifact bytes persisted by the selected store."""


@dataclass(frozen=True)
class StoreLimits:
    """Capacity constraints supplied to an atomic job create."""

    max_pending: int
    """Maximum queued, running, or cancelling jobs accepted by the store."""
    max_retained: int
    """Maximum total jobs retained, including terminal history."""


@dataclass(frozen=True)
class WorkerLease:
    """Opaque worker identity used to fence job ownership."""

    worker_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class ServerActivity:
    """Aggregate job and worker activity exposed by the server."""

    queued_jobs: int
    """Jobs waiting for a worker."""
    running_jobs: int
    """Jobs actively executing."""
    cancelling_jobs: int
    """Jobs still occupying a worker while cancellation completes."""
    online_workers: int
    """Workers with an unexpired shared lease."""
