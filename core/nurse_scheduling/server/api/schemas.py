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
from typing import Literal

from pydantic import BaseModel

from ..config import ServerSettings
from ..jobs.models import Job, JobState, OptimizationOutcome
from ..solver_capabilities import get_solver_capabilities, solver_supports_finish_now


class TimeoutOptionsResponse(BaseModel):
    """Allowed integer range and default for an optimization timeout."""

    default: int
    minimum: int
    maximum: int


class SolverControlOptionsResponse(BaseModel):
    """Running-job controls available for one solver."""

    cancel_running: bool
    finish_now: bool


class SolverChoiceResponse(BaseModel):
    """One solver advertised by this deployment."""

    value: str
    label: str
    compute: Literal["cpu", "gpu"]
    timeout: TimeoutOptionsResponse
    controls: SolverControlOptionsResponse


class SolverOptionsResponse(BaseModel):
    """Allowed solver values and deployment default."""

    default: str
    choices: list[SolverChoiceResponse]


class PrettifyOptionsResponse(BaseModel):
    """Default for schedule prettification."""

    default: bool


class OptimizationOptionsResponse(BaseModel):
    """Backend-defined options accepted when creating optimization jobs."""

    schema_version: Literal["alpha"] = "alpha"
    solver: SolverOptionsResponse
    prettify: PrettifyOptionsResponse

    @classmethod
    def from_settings(cls, settings: ServerSettings) -> "OptimizationOptionsResponse":
        """Project validated settings and canonical solver metadata."""
        timeout = TimeoutOptionsResponse(
            default=settings.default_timeout_seconds,
            minimum=settings.min_timeout_seconds,
            maximum=settings.max_timeout_seconds,
        )
        choices = []
        for solver_id in settings.solver_ids:
            capabilities = get_solver_capabilities(solver_id)
            if capabilities is None:
                raise ValueError(f"Missing capability metadata for configured solver: {solver_id}")
            choices.append(
                SolverChoiceResponse(
                    value=capabilities.value,
                    label=capabilities.label,
                    compute=capabilities.compute,
                    timeout=timeout,
                    controls=SolverControlOptionsResponse(
                        cancel_running=True,
                        finish_now=capabilities.finish_now,
                    ),
                )
            )
        return cls(
            solver=SolverOptionsResponse(default=settings.default_solver, choices=choices),
            prettify=PrettifyOptionsResponse(default=settings.default_prettify),
        )


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
        supports_finish_now = solver_supports_finish_now(job.request.solver)
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
                cancellable=not job.state.terminal and not job.cancel_requested,
                early_completion_available=job.state == JobState.RUNNING
                and supports_finish_now
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
