"""FastAPI backend for nurse scheduling optimization and XLSX export."""

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
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from . import scheduler, exporter
from .solver_interface import SolverProgress


def _get_app_version() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={repo_root}",
                "-C",
                str(repo_root),
                "describe",
                "--tags",
                "--always",
                "--dirty",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "v0.0.0-unknown"


def _should_enable_sentry() -> bool:
    if os.getenv("DISABLE_SENTRY"):
        return False
    # Avoid sending errors from local/unit test runs by default.
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return False
    return True


app_version = _get_app_version()


if _should_enable_sentry():
    import sentry_sdk

    sentry_sdk.init(
        dsn="https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088",
        release=os.getenv("SENTRY_RELEASE", f"nurse-scheduling@{app_version}"),
        # Add data like request headers and IP for users, if applicable;
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # To collect profiles for all profile sessions,
        # set `profile_session_sample_rate` to 1.0.
        profile_session_sample_rate=1.0,
        # Profiles will be automatically collected while
        # there is an active span.
        profile_lifecycle="trace",
        # Enable logs to be sent to Sentry
        enable_logs=True,
    )
    sentry_sdk.set_tag("app", "backend")

# Configure logging to verbose level 1 (verbose levels defined in CLI)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

title = "Nurse Scheduling API"
version = "alpha"

app = FastAPI(title=title, version=version)


class OptimizeJobStatus(str, Enum):
    """Lifecycle status for asynchronous optimization jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
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
    xlsx_bytes: bytes | None = None
    xlsx_filename: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)


OPTIMIZE_JOB_TTL_SECONDS = 30 * 60
OPTIMIZE_MAX_WORKERS = 1
UNEXPECTED_ERROR_VERSION_ADVICE = (
    "If this error was unexpected, check that your frontend and backend versions match. "
    "Older YAML may not work after breaking changes, though we try to preserve compatibility."
)
_optimize_jobs: dict[str, OptimizeJob] = {}
_optimize_jobs_lock = threading.Lock()
_optimize_executor = ThreadPoolExecutor(max_workers=OPTIMIZE_MAX_WORKERS)


def _is_terminal_job_status(status: OptimizeJobStatus) -> bool:
    return status in {
        OptimizeJobStatus.OPTIMAL,
        OptimizeJobStatus.FEASIBLE,
        OptimizeJobStatus.INFEASIBLE,
        OptimizeJobStatus.FAILED,
    }


def _publish_job_event(job: OptimizeJob, event: str, data: dict[str, Any]) -> None:
    with job.condition:
        job.events.append({"event": event, "data": data})
        job.condition.notify_all()


def _cleanup_expired_optimize_jobs(now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
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
            created_at=datetime.now(),
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
        "xlsxReady": job.xlsx_bytes is not None,
        "links": {
            "status": f"/optimize/{job.id}",
            "events": f"/optimize/{job.id}/events",
            "xlsx": f"/optimize/{job.id}/xlsx",
        },
    }


async def _read_optimization_input(
    file: UploadFile | None,
    yaml_content: str | None,
) -> tuple[bytes, str]:
    if file is None and yaml_content is None:
        raise HTTPException(status_code=400, detail="Either 'file' or 'yaml_content' must be provided")

    if file is not None and yaml_content is not None:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'yaml_content', not both")

    if file is not None:
        if not file.filename.endswith((".yaml", ".yml")):
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload a YAML file (.yaml or .yml)")
        return await file.read(), file.filename

    return yaml_content.encode("utf-8"), f"nurse-scheduling-{datetime.now().strftime('%Y%m%d%H%M%S')}.yaml"


def _final_status_from_solver_status(solver_status: str) -> OptimizeJobStatus:
    if solver_status == "OPTIMAL":
        return OptimizeJobStatus.OPTIMAL
    if solver_status == "FEASIBLE":
        return OptimizeJobStatus.FEASIBLE
    if solver_status == "INFEASIBLE":
        return OptimizeJobStatus.INFEASIBLE
    return OptimizeJobStatus.FAILED


def _format_unexpected_error(error: Exception) -> str:
    return f"{error}\n\n{UNEXPECTED_ERROR_VERSION_ADVICE}"


def _capture_optimize_exception(job: OptimizeJob, content: bytes, error: Exception) -> None:
    if not _should_enable_sentry():
        return

    import sentry_sdk

    # Ref: https://docs.sentry.io/platforms/python/enriching-events/scopes/
    with sentry_sdk.new_scope() as scope:
        scope.set_context(
            "schedule_state",
            {
                "attached": True,
                "input_name": job.input_name,
                "job_id": job.id,
                "size_bytes": len(content),
            },
        )
        scope.add_attachment(
            bytes=content,
            filename=job.input_name,
            content_type="application/x-yaml",
        )
        sentry_sdk.capture_exception(error)


def _run_optimize_job(job_id: str, content: bytes) -> None:
    job = _update_optimize_job(job_id, status=OptimizeJobStatus.RUNNING, started_at=datetime.now())
    _publish_job_event(job, "status", {"status": OptimizeJobStatus.RUNNING.value})

    try:

        def publish_progress(payload: SolverProgress) -> None:
            current_job = _get_optimize_job(job_id)
            _update_optimize_job(job_id, score=payload.currentBestScore)
            _publish_job_event(current_job, "progress", payload.to_dict())

        df, _solution, score, solver_status, cell_export_info = scheduler.schedule(
            file_content=content,
            prettify=job.prettify,
            timeout=job.timeout,
            solver=job.solver,
            progress_callback=publish_progress,
        )

        if df is None:
            job = _update_optimize_job(
                job_id,
                status=OptimizeJobStatus.INFEASIBLE,
                solver_status=solver_status,
                finished_at=datetime.now(),
            )
            _publish_job_event(job, "complete", _optimize_job_response(job))
            return

        output_buffer = BytesIO()
        exporter.export_to_excel(df, output_buffer, cell_export_info)
        output_filename = f"{job.input_name.rsplit('.', 1)[0]}.xlsx"
        final_status = _final_status_from_solver_status(str(solver_status))
        job = _update_optimize_job(
            job_id,
            status=final_status,
            score=score,
            solver_status=str(solver_status),
            finished_at=datetime.now(),
            xlsx_bytes=output_buffer.getvalue(),
            xlsx_filename=output_filename,
        )
        _publish_job_event(job, "complete", _optimize_job_response(job))
    except Exception as e:
        logging.error("Error during optimization job %s: %s", job_id, str(e))
        _capture_optimize_exception(job, content, e)
        job = _update_optimize_job(
            job_id,
            status=OptimizeJobStatus.FAILED,
            error=_format_unexpected_error(e),
            finished_at=datetime.now(),
        )
        _publish_job_event(job, "error", _optimize_job_response(job))


def _format_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_optimize_job_events(job: OptimizeJob):
    event_index = 0
    while True:
        heartbeat = False
        with job.condition:
            while event_index >= len(job.events) and not _is_terminal_job_status(job.status):
                job.condition.wait(timeout=15)
                if event_index >= len(job.events):
                    heartbeat = True
                    break

            if heartbeat:
                event = None
            elif event_index < len(job.events):
                event = job.events[event_index]
                event_index += 1
            elif _is_terminal_job_status(job.status):
                event = {"event": "complete", "data": _optimize_job_response(job)}
                event_index += 1
            else:
                event = None

        if event is None:
            yield ": keepalive\n\n"
            continue

        yield _format_sse_event(event["event"], event["data"])
        if event["event"] in {"complete", "error"}:
            return


# Regex to match allowed origins:
# - http://localhost:3000, http://127.0.0.1:3000 (for Next.js local development)
# - https://*.nursescheduling.org (including nursescheduling.org itself)
#   Examples: https://nursescheduling.org, https://dev.nursescheduling.org, https://release-0-1.nursescheduling.org
origin_regex = r"^(http://(localhost|127\.0\.0\.1):3000|https://([a-zA-Z0-9-]+\.)?nursescheduling\.org)$"

expose_headers = [
    "Content-Disposition",
    "X-Schedule-Score",
    "X-Schedule-Status",
]

# Configure CORS to only allow trusted frontend origins in order to
# prevent Cross-Site Request Forgery (CSRF) attacks.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=expose_headers,
)


@app.get("/")
async def root():
    return {
        "message": title,
        "version": version,
        "appVersion": app_version,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": version,
        "apiVersion": version,
        "appVersion": app_version,
    }


@app.post("/optimize", status_code=202)
async def create_optimize_job(
    file: Optional[UploadFile] = File(None, description="YAML file with scheduling data"),
    yaml_content: Optional[str] = Form(None, description="YAML content as a string"),
    prettify: Optional[bool] = Form(None, description="Enable prettier output formatting"),
    timeout: Optional[int] = Form(None, description="Max execution time in seconds"),
    solver: str = Form("ortools/cp-sat", description="Solver selector (e.g., ortools/cp-sat, pulp/cbc, pulp/cuopt)"),
):
    content, input_name = await _read_optimization_input(file, yaml_content)
    job = _create_optimize_job(input_name=input_name, solver=solver, prettify=prettify, timeout=timeout)
    _optimize_executor.submit(_run_optimize_job, job.id, content)
    return _optimize_job_response(job)


@app.get("/optimize/{job_id}")
async def get_optimize_job(job_id: str):
    job = _get_optimize_job(job_id)
    return _optimize_job_response(job)


@app.get("/optimize/{job_id}/events")
async def stream_optimize_job_events(job_id: str):
    job = _get_optimize_job(job_id)
    return StreamingResponse(
        _stream_optimize_job_events(job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/optimize/{job_id}/xlsx")
async def download_optimize_job_xlsx(job_id: str):
    job = _get_optimize_job(job_id)
    if job.xlsx_bytes is None:
        if _is_terminal_job_status(job.status):
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No feasible solution is available.",
                    "status": job.status.value,
                },
            )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Result is not ready yet.",
                "status": job.status.value,
            },
        )

    return StreamingResponse(
        BytesIO(job.xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={job.xlsx_filename}",
            "X-Schedule-Score": str(job.score),
            "X-Schedule-Status": str(job.solver_status),
        },
    )


@app.delete("/optimize/{job_id}")
async def delete_optimize_job(job_id: str):
    _cleanup_expired_optimize_jobs()
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
    return {"deleted": True, "jobId": job_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
