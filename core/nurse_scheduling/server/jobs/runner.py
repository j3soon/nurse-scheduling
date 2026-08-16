"""Adapter from a job request to the synchronous scheduler and XLSX exporter."""

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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timezone
from io import BytesIO
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAMLError

from ... import exporter, scheduler
from ...solver_interface import (
    SchedulePhaseProgress,
    ScheduleProgress,
    serialize_schedule_phase_progress,
    serialize_solver_progress,
)
from .models import Job, JobFailure, OptimizationOutcome, OptimizationResult, StoredArtifact

EventCallback = Callable[[str, dict[str, Any], int | None], None]
StopCallback = Callable[[], bool]


@dataclass(frozen=True)
class RunOutput:
    """Normalized result and optional artifact produced by one execution."""

    result: OptimizationResult
    """Normalized result for a completed scheduling run."""
    artifact: StoredArtifact | None
    """Generated XLSX artifact, absent when no schedule exists."""


RunResult = RunOutput | JobFailure


class OptimizationRunner:
    """Run the scheduling engine without knowing job persistence or HTTP."""

    def run(
        self,
        job: Job,
        input_bytes: bytes,
        *,
        event_callback: EventCallback,
        should_stop: StopCallback | None,
    ) -> RunResult:
        """Run the scheduler and return its output or expected failure.

        Progress and phase changes are forwarded through `event_callback`.
        """

        def publish_progress(payload: ScheduleProgress) -> None:
            """Normalize scheduler progress into job-domain events."""
            if isinstance(payload, SchedulePhaseProgress):
                event_callback("job.phase_changed", serialize_schedule_phase_progress(payload), None)
                return
            data = serialize_solver_progress(payload, include_export_summary=True)
            event_callback("job.progressed", data, payload.currentBestScore)

        try:
            schedule_result = scheduler.schedule(
                file_content=input_bytes,
                prettify=job.request.prettify,
                timeout=job.request.timeout_seconds,
                solver=job.request.solver,
                progress_callback=publish_progress,
                should_stop=should_stop,
            )
        except YAMLError as e:
            return JobFailure(code="invalid_input", message=f"Invalid YAML: {e}")
        except ValidationError as e:
            return JobFailure(code="invalid_input", message=f"Invalid scheduling data: {e}")
        except NotImplementedError as e:
            return JobFailure(code="invalid_input", message=str(e))
        stop_requested_when_solver_returned = should_stop is not None and should_stop()

        normalized_status = schedule_result.solver_status
        if normalized_status == "INFEASIBLE":
            return RunOutput(
                result=OptimizationResult(
                    outcome=OptimizationOutcome.INFEASIBLE,
                    score=None,
                    solver_status=normalized_status,
                    termination_reason="infeasibility_proven",
                ),
                artifact=None,
            )
        if normalized_status == "MODEL_INVALID":
            return JobFailure(code="invalid_model", message="The generated solver model is invalid")
        if normalized_status not in {"OPTIMAL", "FEASIBLE"} or schedule_result.dataframe is None:
            return JobFailure(
                code="no_solution_found",
                message=f"No schedule was produced. Solver status: {normalized_status}",
            )

        output_buffer = BytesIO()
        exporter.export_to_excel(schedule_result.dataframe, output_buffer, schedule_result.cell_export_info)
        created_at = job.created_at.astimezone(timezone.utc)
        output_filename = f"nurse-scheduling-{created_at:%Y%m%dT%H%M%SZ}.xlsx"
        outcome = OptimizationOutcome.OPTIMAL if normalized_status == "OPTIMAL" else OptimizationOutcome.FEASIBLE
        if outcome == OptimizationOutcome.OPTIMAL:
            termination_reason = "optimality_proven"
        elif stop_requested_when_solver_returned:
            termination_reason = "user_requested"
        else:
            termination_reason = "solver_timeout"
        return RunOutput(
            result=OptimizationResult(
                outcome=outcome,
                score=schedule_result.score,
                solver_status=normalized_status,
                termination_reason=termination_reason,
            ),
            artifact=StoredArtifact(
                name=output_filename,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content=output_buffer.getvalue(),
            ),
        )
