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

import logging
import os
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import HTTPException


server_logger = logging.getLogger("nurse_scheduling.server")


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
    client_uuid: str
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
    queue_position: int | None = None
    last_client_heartbeat_at: datetime | None = None
    client_heartbeat_expired: bool = False


_OPTIMIZE_JOB_FIELD_NAMES = frozenset(field.name for field in fields(OptimizeJob))


def _positive_environment_integer(name: str, default: int) -> int:
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


OPTIMIZE_JOB_TTL_SECONDS = 30 * 60
OPTIMIZE_MAX_PENDING_JOBS = 8
OPTIMIZE_MAX_RETAINED_JOBS = 32
OPTIMIZE_SSE_KEEPALIVE_SECONDS = _positive_environment_integer("OPTIMIZE_SSE_KEEPALIVE_SECONDS", 10)
OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS = _positive_environment_integer(
    "OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS", 60
)
OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS = _positive_environment_integer("OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS", 5)
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


def _job_status_event_data(job: OptimizeJob) -> dict[str, Any]:
    return {
        "status": job.status.value,
        "queuePosition": job.queue_position,
    }


def _log_terminal_job(job: OptimizeJob) -> None:
    finished_at = job.finished_at or utc_now()
    started_at = job.started_at or job.created_at
    server_logger.info(
        "[server:job] completed job_id=%s status=%s score=%s duration_seconds=%.3f client_uuid=%s",
        job.id,
        job.status.value,
        job.score,
        (finished_at - started_at).total_seconds(),
        job.client_uuid,
    )


def _refresh_queue_positions() -> None:
    changed_jobs: list[OptimizeJob] = []
    with _optimize_jobs_lock:
        queued_jobs = sorted(
            (job for job in _optimize_jobs.values() if job.status == OptimizeJobStatus.QUEUED),
            key=lambda job: job.created_at,
        )
        positions = {job.id: index for index, job in enumerate(queued_jobs, start=1)}
        for job in _optimize_jobs.values():
            new_position = positions.get(job.id)
            if job.queue_position != new_position:
                job.queue_position = new_position
                changed_jobs.append(job)

    for job in changed_jobs:
        _publish_job_event(job, "status", _job_status_event_data(job))


def _cleanup_expired_optimize_jobs(now: datetime | None = None) -> list[str]:
    now = now or utc_now()
    cutoff = now - timedelta(seconds=OPTIMIZE_JOB_TTL_SECONDS)
    expired_jobs: list[OptimizeJob] = []
    with _optimize_jobs_lock:
        expired_jobs = [
            job for job in _optimize_jobs.values() if job.finished_at is not None and job.finished_at < cutoff
        ]
        for job in expired_jobs:
            del _optimize_jobs[job.id]
    for job in expired_jobs:
        server_logger.info(
            "[server:job] expired job_id=%s status=%s reason=ttl client_uuid=%s",
            job.id,
            job.status.value,
            job.client_uuid,
        )
    return [job.id for job in expired_jobs]


def _enforce_optimize_job_limits() -> None:
    pending_jobs = [job for job in _optimize_jobs.values() if not _is_terminal_job_status(job.status)]
    if len(pending_jobs) >= OPTIMIZE_MAX_PENDING_JOBS:
        server_logger.warning(
            "[server:queue] rejected reason=pending_limit pending_jobs=%s limit=%s",
            len(pending_jobs),
            OPTIMIZE_MAX_PENDING_JOBS,
        )
        raise HTTPException(status_code=429, detail="Too many optimization jobs are already queued or running")

    if len(_optimize_jobs) < OPTIMIZE_MAX_RETAINED_JOBS:
        return

    terminal_jobs = sorted(
        (job for job in _optimize_jobs.values() if _is_terminal_job_status(job.status)),
        key=lambda job: job.finished_at or job.created_at,
    )
    while len(_optimize_jobs) >= OPTIMIZE_MAX_RETAINED_JOBS and terminal_jobs:
        expired_job = terminal_jobs.pop(0)
        del _optimize_jobs[expired_job.id]
        server_logger.info(
            "[server:job] expired job_id=%s status=%s reason=retention_limit client_uuid=%s",
            expired_job.id,
            expired_job.status.value,
            expired_job.client_uuid,
        )

    if len(_optimize_jobs) >= OPTIMIZE_MAX_RETAINED_JOBS:
        server_logger.warning(
            "[server:queue] rejected reason=retained_limit retained_jobs=%s limit=%s",
            len(_optimize_jobs),
            OPTIMIZE_MAX_RETAINED_JOBS,
        )
        raise HTTPException(status_code=429, detail="Too many optimization jobs are retained")


def _get_optimize_job(job_id: str) -> OptimizeJob:
    _cleanup_expired_optimize_jobs()
    with _optimize_jobs_lock:
        job = _optimize_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Optimization job not found")
    return job


def _create_optimize_job(
    input_name: str,
    client_uuid: str,
    solver: str,
    prettify: bool | None,
    timeout: int | None,
) -> OptimizeJob:
    _cleanup_expired_optimize_jobs()
    with _optimize_jobs_lock:
        _enforce_optimize_job_limits()
        while True:
            job_id = f"opt_{uuid.uuid4().hex}"
            if job_id not in _optimize_jobs:
                break

        job = OptimizeJob(
            id=job_id,
            status=OptimizeJobStatus.QUEUED,
            created_at=utc_now(),
            input_name=input_name,
            client_uuid=client_uuid,
            solver=solver,
            prettify=prettify,
            timeout=timeout,
        )
        job.last_client_heartbeat_at = job.created_at
        _optimize_jobs[job.id] = job
    _refresh_queue_positions()
    server_logger.info(
        "[server:job] queued job_id=%s solver=%s timeout=%s input_name=%s queue_position=%s client_uuid=%s",
        job.id,
        job.solver,
        job.timeout,
        job.input_name,
        job.queue_position,
        job.client_uuid,
    )
    return job


def _update_optimize_job(job_id: str, **updates) -> OptimizeJob:
    unknown_fields = updates.keys() - _OPTIMIZE_JOB_FIELD_NAMES
    if unknown_fields:
        raise ValueError(f"Unknown optimization job fields: {', '.join(sorted(unknown_fields))}")

    with _optimize_jobs_lock:
        job = _optimize_jobs[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
    return job


def _update_optimize_job_if_present(job_id: str, **updates) -> OptimizeJob | None:
    """Update a job if it has not been deleted by a concurrent request."""
    unknown_fields = updates.keys() - _OPTIMIZE_JOB_FIELD_NAMES
    if unknown_fields:
        raise ValueError(f"Unknown optimization job fields: {', '.join(sorted(unknown_fields))}")

    with _optimize_jobs_lock:
        job = _optimize_jobs.get(job_id)
        if job is None:
            return None
        for key, value in updates.items():
            setattr(job, key, value)
    return job


def _finish_optimize_job(job_id: str, event: str, **updates) -> OptimizeJob:
    job = _finish_optimize_job_if_present(job_id, event, **updates)
    if job is None:
        raise KeyError(job_id)
    return job


def _validate_terminal_job_update(event: str, updates: dict[str, Any]) -> None:
    unknown_fields = updates.keys() - _OPTIMIZE_JOB_FIELD_NAMES
    if unknown_fields:
        raise ValueError(f"Unknown optimization job fields: {', '.join(sorted(unknown_fields))}")
    status = updates.get("status")
    if not isinstance(status, OptimizeJobStatus) or not _is_terminal_job_status(status):
        raise ValueError("A terminal optimization job status is required")
    if event not in {"complete", "error"}:
        raise ValueError("A terminal optimization job event is required")


def _finish_optimize_job_locked(job: OptimizeJob, event: str, updates: dict[str, Any]) -> None:
    with job.condition:
        for key, value in updates.items():
            setattr(job, key, value)
        job.queue_position = None
        job.events.append({"event": event, "data": _optimize_job_response(job)})
        job.condition.notify_all()


def _finish_optimize_job_if_present(job_id: str, event: str, **updates) -> OptimizeJob | None:
    """Atomically update a terminal job and publish its terminal event."""
    _validate_terminal_job_update(event, updates)

    with _optimize_jobs_lock:
        job = _optimize_jobs.get(job_id)
        if job is None:
            return None
        _finish_optimize_job_locked(job, event, updates)
    return job


def _is_job_stop_requested(job_id: str) -> bool:
    job = _get_optimize_job(job_id)
    return job.cancel_requested or job.finish_now_requested


def _request_optimize_job_stop(job_id: str, *, finish_now: bool) -> OptimizeJob:
    complete_immediately = False
    terminal_updates = {
        "status": OptimizeJobStatus.CANCELLED,
        "cancel_requested": True,
        "error": "Optimization cancelled.",
        "finished_at": utc_now(),
    }
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
        if job.status != OptimizeJobStatus.QUEUED and not _solver_supports_job_stop(job.solver):
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
        elif job.status == OptimizeJobStatus.QUEUED:
            _finish_optimize_job_locked(job, "complete", terminal_updates)
            complete_immediately = True
        else:
            job.cancel_requested = True
            job.status = OptimizeJobStatus.CANCELLING
    server_logger.info(
        "[server:job] %s job_id=%s status=%s client_uuid=%s",
        "finish-now-requested" if finish_now else "cancel-requested",
        job.id,
        job.status.value,
        job.client_uuid,
    )
    if complete_immediately:
        _refresh_queue_positions()
        _log_terminal_job(job)
    elif not finish_now:
        _publish_job_event(job, "status", _job_status_event_data(job))
    return job


def _record_client_heartbeat(job_id: str, now: datetime | None = None) -> OptimizeJob:
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
        job.last_client_heartbeat_at = now or utc_now()
    return job


def _cancel_jobs_with_expired_heartbeats(now: datetime | None = None) -> list[str]:
    now = now or utc_now()
    cutoff = now - timedelta(seconds=OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS)
    expired_jobs: list[OptimizeJob] = []
    with _optimize_jobs_lock:
        for job in _optimize_jobs.values():
            if (
                not _is_terminal_job_status(job.status)
                and job.last_client_heartbeat_at is not None
                and job.last_client_heartbeat_at <= cutoff
            ):
                job.client_heartbeat_expired = True
                job.cancel_requested = True
                job.error = "Optimization cancelled because the client heartbeat expired."
                if job.status == OptimizeJobStatus.QUEUED:
                    _finish_optimize_job_locked(
                        job,
                        "complete",
                        {
                            "status": OptimizeJobStatus.CANCELLED,
                            "cancel_requested": True,
                            "client_heartbeat_expired": True,
                            "error": job.error,
                            "finished_at": now,
                        },
                    )
                else:
                    job.status = OptimizeJobStatus.CANCELLING
                expired_jobs.append(job)

    if expired_jobs:
        _refresh_queue_positions()
    for job in expired_jobs:
        server_logger.warning(
            "[server:job] heartbeat-expired job_id=%s status=%s action=cancel-requested client_uuid=%s",
            job.id,
            job.status.value,
            job.client_uuid,
        )
        if _is_terminal_job_status(job.status):
            _log_terminal_job(job)
        else:
            _publish_job_event(job, "status", _job_status_event_data(job))
    return [job.id for job in expired_jobs]


def _run_client_heartbeat_watchdog() -> None:
    while True:
        time.sleep(OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS)
        _cancel_jobs_with_expired_heartbeats()


def _optimize_job_response(job: OptimizeJob) -> dict[str, Any]:
    return {
        "jobId": job.id,
        "status": job.status.value,
        "queuePosition": job.queue_position,
        "inputName": job.input_name,
        "solver": job.solver,
        "prettify": job.prettify,
        "timeout": job.timeout,
        "score": job.score,
        "solverStatus": job.solver_status,
        "error": job.error,
        "cancelRequested": job.cancel_requested,
        "finishNowRequested": job.finish_now_requested,
        "clientHeartbeatExpired": job.client_heartbeat_expired,
        "xlsxReady": job.xlsx_bytes is not None,
        "links": {
            "status": f"/optimize/{job.id}",
            "events": f"/optimize/{job.id}/events",
            "heartbeat": f"/optimize/{job.id}/heartbeat",
            "xlsx": f"/optimize/{job.id}/xlsx",
        },
    }


class InMemoryOptimizeJobStore:
    """Process-local optimization job store.

    This interface keeps FastAPI routes decoupled from the current module-level
    dictionaries and locks. A later Redis-backed implementation should expose
    the same operations while moving state, events, and artifacts out of process
    memory.
    """

    def cleanup_expired_jobs(self, now: datetime | None = None) -> list[str]:
        return _cleanup_expired_optimize_jobs(now)

    def create_job(
        self,
        input_name: str,
        client_uuid: str,
        solver: str,
        prettify: bool | None,
        timeout: int | None,
    ) -> OptimizeJob:
        return _create_optimize_job(input_name, client_uuid, solver, prettify, timeout)

    def get_job(self, job_id: str) -> OptimizeJob:
        return _get_optimize_job(job_id)

    def update_job(self, job_id: str, **updates) -> OptimizeJob:
        return _update_optimize_job(job_id, **updates)

    def finish_job(self, job_id: str, event: str, **updates) -> OptimizeJob:
        return _finish_optimize_job(job_id, event, **updates)

    def finish_job_if_present(self, job_id: str, event: str, **updates) -> OptimizeJob | None:
        return _finish_optimize_job_if_present(job_id, event, **updates)

    def refresh_queue_positions(self) -> None:
        _refresh_queue_positions()

    def publish_event(self, job: OptimizeJob, event: str, data: dict[str, Any]) -> None:
        _publish_job_event(job, event, data)

    def status_event_data(self, job: OptimizeJob) -> dict[str, Any]:
        return _job_status_event_data(job)

    def job_response(self, job: OptimizeJob) -> dict[str, Any]:
        return _optimize_job_response(job)

    def stream_events(self, job_id: str, keepalive_seconds: int) -> Iterator[dict[str, Any] | None]:
        job = self.get_job(job_id)
        event_index = 0
        while True:
            heartbeat = False
            with job.condition:
                while event_index >= len(job.events) and not _is_terminal_job_status(job.status):
                    job.condition.wait(timeout=keepalive_seconds)
                    if event_index >= len(job.events):
                        heartbeat = True
                        break

                if heartbeat:
                    event = None
                elif event_index < len(job.events):
                    event = job.events[event_index]
                    event_index += 1
                elif _is_terminal_job_status(job.status):
                    terminal_event = "error" if job.status == OptimizeJobStatus.FAILED else "complete"
                    event = {"event": terminal_event, "data": self.job_response(job)}
                    event_index += 1
                else:
                    event = None

            yield event
            if event is not None and event["event"] in {"complete", "error"}:
                return

    def request_stop(self, job_id: str, *, finish_now: bool) -> OptimizeJob:
        return _request_optimize_job_stop(job_id, finish_now=finish_now)

    def record_client_heartbeat(self, job_id: str, now: datetime | None = None) -> OptimizeJob:
        return _record_client_heartbeat(job_id, now)

    def cancel_jobs_with_expired_heartbeats(self, now: datetime | None = None) -> list[str]:
        return _cancel_jobs_with_expired_heartbeats(now)

    def is_job_stop_requested(self, job_id: str) -> bool:
        return _is_job_stop_requested(job_id)

    def delete_job(self, job_id: str) -> OptimizeJob:
        self.cleanup_expired_jobs()
        with _optimize_jobs_lock:
            job = _optimize_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Optimization job not found")
            if not _is_terminal_job_status(job.status):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Cannot delete a running optimization job.",
                        "status": job.status.value,
                    },
                )
            del _optimize_jobs[job_id]
        server_logger.info(
            "[server:job] deleted job_id=%s status=%s client_uuid=%s",
            job.id,
            job.status.value,
            job.client_uuid,
        )
        return job


optimize_job_store = InMemoryOptimizeJobStore()


if OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS > OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS:
    raise ValueError("OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS must not exceed OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS")
threading.Thread(target=_run_client_heartbeat_watchdog, name="optimize-client-heartbeat", daemon=True).start()
