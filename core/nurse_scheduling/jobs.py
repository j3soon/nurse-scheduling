"""In-memory optimization job state for the FastAPI backend."""

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

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import HTTPException


class OptimizeJobStatus(str, Enum):
    """Lifecycle status for asynchronous optimization jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class OptimizeJob:
    """In-memory state for one optimization job."""

    id: str
    status: OptimizeJobStatus
    created_at: datetime
    input_name: str
    solver: str
    prettify: bool | None
    timeout: int | None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    score: int | None = None
    solver_status: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    finish_now_requested: bool = False
    xlsx_bytes: bytes | None = None
    xlsx_filename: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)


OPTIMIZE_JOB_TTL_SECONDS = 30 * 60
_optimize_jobs: dict[str, OptimizeJob] = {}
_optimize_jobs_lock = threading.Lock()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for job state."""
    return datetime.now(UTC)


def _is_terminal_job_status(status: OptimizeJobStatus) -> bool:
    return status in {
        OptimizeJobStatus.OPTIMAL,
        OptimizeJobStatus.FEASIBLE,
        OptimizeJobStatus.INFEASIBLE,
        OptimizeJobStatus.CANCELLED,
        OptimizeJobStatus.FAILED,
    }


def _solver_supports_job_stop(solver: str) -> bool:
    return solver == "ortools/cp-sat"


def _publish_job_event(job: OptimizeJob, event: str, data: dict[str, Any]) -> None:
    with job.condition:
        job.events.append({"event": event, "data": data})
        job.condition.notify_all()


def _cleanup_expired_optimize_jobs(now: datetime | None = None) -> list[str]:
    now = now or utc_now()
    cutoff = now - timedelta(seconds=OPTIMIZE_JOB_TTL_SECONDS)
    with _optimize_jobs_lock:
        expired_job_ids = [
            job_id for job_id, job in _optimize_jobs.items() if job.finished_at is not None and job.finished_at < cutoff
        ]
        for job_id in expired_job_ids:
            del _optimize_jobs[job_id]
    return expired_job_ids


def _get_optimize_job(job_id: str) -> OptimizeJob:
    _cleanup_expired_optimize_jobs()
    with _optimize_jobs_lock:
        job = _optimize_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Optimization job not found")
    return job


def _create_optimize_job(input_name: str, solver: str, prettify: bool | None, timeout: int | None) -> OptimizeJob:
    _cleanup_expired_optimize_jobs()
    with _optimize_jobs_lock:
        while True:
            job_id = f"opt_{uuid.uuid4().hex}"
            if job_id not in _optimize_jobs:
                break

        job = OptimizeJob(
            id=job_id,
            status=OptimizeJobStatus.QUEUED,
            created_at=utc_now(),
            input_name=input_name,
            solver=solver,
            prettify=prettify,
            timeout=timeout,
        )
        _optimize_jobs[job.id] = job
    _publish_job_event(job, "status", {"status": job.status.value})
    return job


def _update_optimize_job(job_id: str, **updates) -> OptimizeJob:
    with _optimize_jobs_lock:
        job = _optimize_jobs[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
    return job


def _is_job_stop_requested(job_id: str) -> bool:
    job = _get_optimize_job(job_id)
    return job.cancel_requested or job.finish_now_requested


def _request_optimize_job_stop(job_id: str, *, finish_now: bool) -> OptimizeJob:
    with _optimize_jobs_lock:
        job = _optimize_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Optimization job not found")
        if _is_terminal_job_status(job.status):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Optimization job has already finished.",
                    "status": job.status.value,
                },
            )
        if not _solver_supports_job_stop(job.solver):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This solver does not support cancelling or finishing early.",
                    "solver": job.solver,
                    "status": job.status.value,
                },
            )
        if finish_now:
            job.finish_now_requested = True
        else:
            job.cancel_requested = True
            job.status = OptimizeJobStatus.CANCELLING
    if not finish_now:
        _publish_job_event(job, "status", {"status": job.status.value})
    return job


def _optimize_job_response(job: OptimizeJob) -> dict[str, Any]:
    return {
        "jobId": job.id,
        "status": job.status.value,
        "inputName": job.input_name,
        "solver": job.solver,
        "prettify": job.prettify,
        "timeout": job.timeout,
        "score": job.score,
        "solverStatus": job.solver_status,
        "error": job.error,
        "cancelRequested": job.cancel_requested,
        "finishNowRequested": job.finish_now_requested,
        "xlsxReady": job.xlsx_bytes is not None,
        "links": {
            "status": f"/optimize/{job.id}",
            "events": f"/optimize/{job.id}/events",
            "xlsx": f"/optimize/{job.id}/xlsx",
        },
    }
