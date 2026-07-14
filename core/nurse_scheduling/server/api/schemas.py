"""Pydantic request and response models for optimization jobs."""

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

from datetime import datetime

from pydantic import BaseModel

from ..jobs.models import Job, JobState, OptimizationOutcome, solver_supports_stop


class JobRequestResponse(BaseModel):
    """Public execution inputs retained with a job."""

    input_name: str
    """Original input filename."""
    solver: str
    """Selected solver identifier."""
    prettify: bool | None
    """Requested schedule-prettification preference."""
    timeout_seconds: int
    """Configured optimization timeout."""


class OptimizationResultResponse(BaseModel):
    """Public result of a normally completed optimization."""

    outcome: OptimizationOutcome
    """Normalized optimization outcome."""
    score: int | None
    """Best objective score when a schedule exists."""
    solver_status: str
    """Original solver status."""
    termination_reason: str | None
    """Normalized reason solver execution stopped."""


class JobErrorResponse(BaseModel):
    """Structured failure attached to a terminal job."""

    code: str
    """Stable machine-readable failure code."""
    message: str
    """Human-readable failure explanation."""


class JobControlsResponse(BaseModel):
    """Operations currently available for a job."""

    cancellable: bool
    """Whether the client may currently request cancellation."""
    early_completion_available: bool
    """Whether the client may request the current feasible result."""


class JobLinksResponse(BaseModel):
    """Relative API links associated with a job."""

    self: str
    """Current job representation."""
    events: str
    """Replayable server-sent event stream."""
    cancellation: str
    """Cancellation control endpoint."""
    early_completion: str
    """Early-completion control endpoint."""
    schedule: str | None
    """Download endpoint, available only after an artifact is produced."""


class JobResponse(BaseModel):
    """Complete public representation of one optimization job."""

    id: str
    """Stable high-entropy job identifier."""
    state: JobState
    """Current execution lifecycle state."""
    terminal: bool
    """Whether the lifecycle has ended."""
    queue_position: int | None
    """Current one-based position while queued."""
    created_at: datetime
    """Time the job entered the store."""
    started_at: datetime | None
    """Time a worker claimed the job."""
    finished_at: datetime | None
    """Time the job entered a terminal state."""
    request: JobRequestResponse
    """Retained execution inputs."""
    result: OptimizationResultResponse | None
    """Normal optimization result, when completed."""
    error: JobErrorResponse | None
    """Structured failure, when failed or cancelled."""
    controls: JobControlsResponse
    """Operations currently permitted by job state and solver."""
    links: JobLinksResponse
    """Related API resources and controls."""

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        """Project a transport-independent job into its public API shape."""
        supports_stop = solver_supports_stop(job.request.solver)
        return cls(
            id=job.id,
            state=job.state,
            terminal=job.state.terminal,
            queue_position=job.queue_position,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            request=JobRequestResponse(
                input_name=job.request.input_name,
                solver=job.request.solver,
                prettify=job.request.prettify,
                timeout_seconds=job.request.timeout_seconds,
            ),
            result=(
                OptimizationResultResponse(
                    outcome=job.result.outcome,
                    score=job.result.score,
                    solver_status=job.result.solver_status,
                    termination_reason=job.result.termination_reason,
                )
                if job.result is not None
                else None
            ),
            error=(
                JobErrorResponse(code=job.failure.code, message=job.failure.message)
                if job.failure is not None
                else None
            ),
            controls=JobControlsResponse(
                cancellable=not job.state.terminal
                and (job.state == JobState.QUEUED or supports_stop)
                and not job.cancel_requested,
                early_completion_available=job.state == JobState.RUNNING
                and supports_stop
                and not job.early_completion_requested,
            ),
            links=JobLinksResponse(
                self=f"/optimize/{job.id}",
                events=f"/optimize/{job.id}/events",
                cancellation=f"/optimize/{job.id}/cancel",
                early_completion=f"/optimize/{job.id}/finish-now",
                schedule=f"/optimize/{job.id}/xlsx" if job.artifact_name is not None else None,
            ),
        )


class ErrorDetail(BaseModel):
    """Stable JSON error details returned by the API."""

    code: str
    """Machine-readable application error code."""
    message: str
    """Human-readable error explanation."""


class ErrorResponse(BaseModel):
    """Envelope used for application-level JSON errors."""

    error: ErrorDetail
    """Structured error details."""
