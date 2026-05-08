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
import asyncio
import os
import subprocess
import sys
from datetime import datetime
from io import BytesIO
from queue import Empty
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, BackgroundTasks
from typing import Optional
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from . import scheduler, exporter
from .jobs import OptimizationJobManager, format_sse
from .progress import ProgressEvent


def _get_app_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
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

job_manager = OptimizationJobManager()

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


# TODO: Check args
@app.post("/optimize-and-export-xlsx")
async def optimize_and_export_xlsx(
    file: Optional[UploadFile] = File(None, description="YAML file with scheduling data"),
    yaml_content: Optional[str] = Form(None, description="YAML content as a string"),
    prettify: Optional[bool] = Form(None, description="Enable prettier output formatting"),
    timeout: Optional[int] = Form(None, description="Max execution time in seconds"),
    solver: str = Form("ortools/cp-sat", description="Solver selector (e.g., ortools/cp-sat, pulp/cbc, pulp/cuopt)"),
):
    """
    Optimize a nurse schedule from a YAML file or YAML string, and return an XLSX file.

    Either `file` or `yaml_content` must be provided (not both).
    """
    # Validate that exactly one input method is provided
    if file is None and yaml_content is None:
        raise HTTPException(status_code=400, detail="Either 'file' or 'yaml_content' must be provided")

    if file is not None and yaml_content is not None:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'yaml_content', not both")

    # Read content from file or use provided yaml_content
    if file is not None:
        # Validate that the uploaded file is a YAML file (sanity check, not for security)
        if not file.filename.endswith((".yaml", ".yml")):
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload a YAML file (.yaml or .yml)")
        content = await file.read()
        input_name = file.filename
    else:
        # Use yaml_content string directly
        content = yaml_content.encode("utf-8")
        input_name = f"nurse-scheduling-{datetime.now().strftime('%Y%m%d%H%M%S')}.yaml"

    logging.info("Processing schedule optimization...")
    logging.info(f"Input: {input_name}")
    logging.info(
        "Prettify: %s, Timeout: %s, Solver: selector=%s",
        prettify,
        timeout,
        solver,
    )

    try:
        # Run the scheduler with file content directly
        # TODO(security): May need to add security checks to prevent injection attacks or misuse
        df, solution, score, status, cell_export_info = scheduler.schedule(
            file_content=content,
            prettify=prettify,
            timeout=timeout,
            solver=solver,
        )
    except NotImplementedError as e:
        # User input error: unsupported apiVersion or other unsupported scenario feature.
        logging.warning(f"Unsupported request: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Unsupported API version: {str(e)}")
    except ValidationError as e:
        # User-supplied scheduling data failed schema validation -> HTTP 400
        logging.error(f"Invalid scheduling data: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid scheduling data: {str(e)}")
    except Exception as e:
        # TODO(security): Returning the error message to the client may be a security risk
        logging.error(f"Error during optimization: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during optimization: {str(e)}")

    if df is None:
        raise HTTPException(status_code=400, detail="No solution found. The constraints may be too restrictive.")

    # Export to Excel in memory
    output_buffer = BytesIO()
    exporter.export_to_excel(df, output_buffer, cell_export_info)

    logging.info(f"Optimization complete. Score: {score}, Status: {status}")

    # Generate output filename
    base_filename = input_name.rsplit(".", 1)[0]
    output_filename = f"{base_filename}.xlsx"

    # Return the file from memory
    return StreamingResponse(
        output_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={output_filename}",
            "X-Schedule-Score": str(score),
            "X-Schedule-Status": str(status),
        },
    )


def run_optimization_job(
    job_id: str,
    content: bytes,
    prettify: Optional[bool],
    timeout: Optional[int],
    solver: str,
) -> None:
    job = job_manager.get(job_id)
    if job is None:
        return

    def emit(event: ProgressEvent) -> None:
        if event.type == "completed":
            job.emit(ProgressEvent(
                type="phase",
                code="schedule_completed",
                message="Schedule solved; preparing result file",
                progress=0.98,
                score=event.score,
            ))
            return
        job.emit(event)

    try:
        df, _solution, score, status, cell_export_info = scheduler.schedule(
            file_content=content,
            prettify=prettify,
            timeout=timeout,
            solver=solver,
            progress=emit,
        )
    except Exception as e:
        logging.error("Error during optimization job %s: %s", job_id, str(e))
        job.fail(f"Error during optimization: {str(e)}")
        return

    if df is None:
        job.fail("No solution found. The constraints may be too restrictive.")
        return

    output_buffer = BytesIO()
    exporter.export_to_excel(df, output_buffer, cell_export_info)
    output_filename = f"nurse-scheduling-{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    job.complete(
        filename=output_filename,
        xlsx_bytes=output_buffer.getvalue(),
        score=score,
        solver_status=status,
    )


@app.post("/optimization-jobs")
async def create_optimization_job(
    background_tasks: BackgroundTasks,
    yaml_content: str = Form(..., description="YAML content as a string"),
    prettify: Optional[bool] = Form(None, description="Enable prettier output formatting"),
    timeout: Optional[int] = Form(None, description="Max execution time in seconds"),
    solver: str = Form("ortools/cp-sat", description="Solver selector (e.g., ortools/cp-sat, pulp/cbc, pulp/cuopt)"),
):
    job = job_manager.create()
    background_tasks.add_task(
        run_optimization_job,
        job.id,
        yaml_content.encode("utf-8"),
        prettify,
        timeout,
        solver,
    )
    return {"job_id": job.id}


@app.get("/optimization-jobs/{job_id}/events")
async def stream_optimization_events(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            try:
                event = await asyncio.to_thread(job.events.get, True, 0.5)
            except Empty:
                if job.status in ("completed", "failed") and job.events.empty():
                    break
                yield ": ping\n\n"
                continue

            yield format_sse(event)
            if event.type in ("completed", "failed"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/optimization-jobs/{job_id}/result")
async def download_optimization_result(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "failed":
        raise HTTPException(status_code=400, detail=job.error or "Optimization failed")
    if job.status != "completed" or job.xlsx_bytes is None:
        raise HTTPException(status_code=409, detail="Job is not completed")

    return StreamingResponse(
        BytesIO(job.xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={job.filename}",
            "X-Schedule-Score": str(job.score),
            "X-Schedule-Status": str(job.solver_status),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
