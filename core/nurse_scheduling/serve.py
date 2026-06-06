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
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import scheduler, exporter
from . import jobs as optimize_jobs_state
from .jobs import (
    OptimizeJob,
    OptimizeJobStatus,
    _cleanup_expired_optimize_jobs,
    _create_optimize_job,
    _get_optimize_job,
    _is_job_stop_requested,
    _is_terminal_job_status,
    _job_status_event_data,
    _optimize_job_response,
    _optimize_jobs,
    _optimize_jobs_lock,
    _publish_job_event,
    _record_client_heartbeat,
    _refresh_queue_positions,
    _request_optimize_job_stop,
    _solver_supports_job_stop,
    _update_optimize_job,
    utc_now,
)
from .solver_interface import (
    SchedulePhaseProgress,
    ScheduleProgress,
    serialize_schedule_phase_progress,
    serialize_solver_progress,
)
from .sentry import capture_invalid_request, capture_optimize_exception, init_sentry


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


app_version = _get_app_version()


init_sentry(app_version)

# Keep API output focused on server behavior. Solver progress is delivered to
# clients through job events and remains available from the CLI's verbose logs.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
server_logger = logging.getLogger("nurse_scheduling.server")
server_logger.setLevel(logging.INFO)

title = "Nurse Scheduling API"
version = "alpha"

app = FastAPI(title=title, version=version)

# Ref: https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions


@app.exception_handler(RequestValidationError)
async def sentry_request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    capture_invalid_request(request, 422, exc.errors())
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(StarletteHTTPException)
async def sentry_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    if 400 <= exc.status_code < 500:
        capture_invalid_request(request, exc.status_code, exc.detail)
    return await http_exception_handler(request, exc)


MAX_OPTIMIZATION_YAML_BYTES = 2 * 1024 * 1024
DEFAULT_OPTIMIZATION_TIMEOUT_SECONDS = 5 * 60
MAX_OPTIMIZATION_TIMEOUT_SECONDS = 60 * 60
OPTIMIZE_MAX_PENDING_JOBS = optimize_jobs_state.OPTIMIZE_MAX_PENDING_JOBS
OPTIMIZE_MAX_RETAINED_JOBS = optimize_jobs_state.OPTIMIZE_MAX_RETAINED_JOBS
OPTIMIZE_JOB_TTL_SECONDS = optimize_jobs_state.OPTIMIZE_JOB_TTL_SECONDS
OPTIMIZE_SSE_KEEPALIVE_SECONDS = optimize_jobs_state.OPTIMIZE_SSE_KEEPALIVE_SECONDS
OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS = optimize_jobs_state.OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS
OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS = optimize_jobs_state.OPTIMIZE_CLIENT_LIVENESS_CHECK_SECONDS
OPTIMIZE_MAX_WORKERS = 1
UNEXPECTED_ERROR_VERSION_ADVICE = (
    "If this error was unexpected, check that your frontend and backend versions match. "
    "Older YAML may not work after breaking changes, though we try to preserve compatibility."
)
_optimize_executor = ThreadPoolExecutor(max_workers=OPTIMIZE_MAX_WORKERS)
uuid = optimize_jobs_state.uuid
_cancel_jobs_with_expired_heartbeats = optimize_jobs_state._cancel_jobs_with_expired_heartbeats


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
        content = await file.read()
        input_name = file.filename
    else:
        content = yaml_content.encode("utf-8")
        input_name = f"nurse-scheduling-{datetime.now().strftime('%Y%m%d%H%M%S')}.yaml"

    if len(content) > MAX_OPTIMIZATION_YAML_BYTES:
        raise HTTPException(status_code=413, detail="Scheduling YAML is too large")
    return content, input_name


def _normalize_optimization_timeout(timeout: int | None) -> int:
    if timeout is None:
        return DEFAULT_OPTIMIZATION_TIMEOUT_SECONDS
    if timeout > MAX_OPTIMIZATION_TIMEOUT_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"Optimization timeout must be at most {MAX_OPTIMIZATION_TIMEOUT_SECONDS} seconds",
        )
    return timeout


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


def _job_cancellation_error(job: OptimizeJob) -> str:
    return job.error or "Optimization cancelled."


def _log_job_completed(job: OptimizeJob) -> None:
    started_at = job.started_at or job.created_at
    finished_at = job.finished_at or utc_now()
    duration_seconds = (finished_at - started_at).total_seconds()
    server_logger.info(
        "[server:job] completed job_id=%s status=%s score=%s duration_seconds=%.3f",
        job.id,
        job.status.value,
        job.score,
        duration_seconds,
    )


def _run_optimize_job(job_id: str, content: bytes) -> None:
    current_job = _get_optimize_job(job_id)
    if current_job.cancel_requested:
        if _is_terminal_job_status(current_job.status):
            return
        job = _update_optimize_job(
            job_id,
            status=OptimizeJobStatus.CANCELLED,
            error=_job_cancellation_error(current_job),
            finished_at=utc_now(),
        )
        _publish_job_event(job, "complete", _optimize_job_response(job))
        _refresh_queue_positions()
        _log_job_completed(job)
        return

    job = _update_optimize_job(job_id, status=OptimizeJobStatus.RUNNING, started_at=utc_now())
    _refresh_queue_positions()
    queue_wait_seconds = (job.started_at - job.created_at).total_seconds()
    server_logger.info(
        "[server:job] started job_id=%s solver=%s queue_wait_seconds=%.3f",
        job.id,
        job.solver,
        queue_wait_seconds,
    )

    try:

        def publish_progress(payload: ScheduleProgress) -> None:
            current_job = _get_optimize_job(job_id)
            if isinstance(payload, SchedulePhaseProgress):
                _publish_job_event(current_job, "phase", serialize_schedule_phase_progress(payload))
                return
            _update_optimize_job(job_id, score=payload.currentBestScore)
            _publish_job_event(current_job, "progress", serialize_solver_progress(payload, include_export_summary=True))

        should_stop = None
        if _solver_supports_job_stop(job.solver):

            def should_stop() -> bool:
                return _is_job_stop_requested(job_id)

        df, _solution, score, solver_status, cell_export_info = scheduler.schedule(
            file_content=content,
            prettify=job.prettify,
            timeout=job.timeout,
            solver=job.solver,
            progress_callback=publish_progress,
            should_stop=should_stop,
        )

        current_job = _get_optimize_job(job_id)
        if current_job.cancel_requested:
            job = _update_optimize_job(
                job_id,
                status=OptimizeJobStatus.CANCELLED,
                error=_job_cancellation_error(current_job),
                finished_at=utc_now(),
            )
            _publish_job_event(job, "complete", _optimize_job_response(job))
            _refresh_queue_positions()
            _log_job_completed(job)
            return

        if df is None:
            job = _update_optimize_job(
                job_id,
                status=OptimizeJobStatus.INFEASIBLE,
                solver_status=solver_status,
                finished_at=utc_now(),
            )
            _publish_job_event(job, "complete", _optimize_job_response(job))
            _refresh_queue_positions()
            _log_job_completed(job)
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
            finished_at=utc_now(),
            xlsx_bytes=output_buffer.getvalue(),
            xlsx_filename=output_filename,
        )
        _publish_job_event(job, "complete", _optimize_job_response(job))
        _refresh_queue_positions()
        _log_job_completed(job)
    except Exception as e:
        capture_optimize_exception(job, content, e)
        job = _update_optimize_job(
            job_id,
            status=OptimizeJobStatus.FAILED,
            error=_format_unexpected_error(e),
            finished_at=utc_now(),
        )
        _publish_job_event(job, "error", _optimize_job_response(job))
        _refresh_queue_positions()
        duration_seconds = (job.finished_at - (job.started_at or job.created_at)).total_seconds()
        server_logger.error(
            "[server:job] failed job_id=%s error=%s duration_seconds=%.3f",
            job.id,
            str(e),
            duration_seconds,
        )


def _format_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_optimize_job_events(job: OptimizeJob):
    event_index = 0
    while True:
        heartbeat = False
        with job.condition:
            while event_index >= len(job.events) and not _is_terminal_job_status(job.status):
                job.condition.wait(timeout=OPTIMIZE_SSE_KEEPALIVE_SECONDS)
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
    timeout = _normalize_optimization_timeout(timeout)
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


@app.post("/optimize/{job_id}/heartbeat")
async def heartbeat_optimize_job(job_id: str):
    job = _record_client_heartbeat(job_id)
    return {"jobId": job.id, "status": job.status.value}


@app.post("/optimize/{job_id}/cancel")
async def cancel_optimize_job(job_id: str):
    job = _request_optimize_job_stop(job_id, finish_now=False)
    return _optimize_job_response(job)


@app.post("/optimize/{job_id}/finish-now")
async def finish_optimize_job_now(job_id: str):
    job = _request_optimize_job_stop(job_id, finish_now=True)
    event_data = _job_status_event_data(job)
    event_data["finishNowRequested"] = True
    _publish_job_event(job, "status", event_data)
    return _optimize_job_response(job)


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
    server_logger.info("[server:job] deleted job_id=%s status=%s", job.id, job.status.value)
    return {"deleted": True, "jobId": job_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
