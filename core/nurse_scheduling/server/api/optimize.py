"""HTTP routes for creating and controlling optimization jobs."""

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

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from ... import scheduler
from ..config import ServerSettings
from ..jobs.controller import JobController
from ..jobs.models import JobState
from ..solver_capabilities import solver_supports_finish_now
from .schemas import JobResponse
from .sse import format_sse_event

router = APIRouter()
CLIENT_ID_COOKIE_NAME = "nurse_scheduling_client_id"
"""Cookie used to correlate jobs from the same browser for diagnostics."""
CLIENT_ID_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
"""Seven-day correlation lifetime; the cookie does not control job liveness."""


def _controller(request: Request) -> JobController:
    """Return the application-scoped job controller."""
    return request.app.state.job_controller


def _settings(request: Request) -> ServerSettings:
    """Return the validated application-scoped server settings."""
    return request.app.state.settings


async def _read_input(
    file: UploadFile | None,
    yaml_content: str | None,
    max_bytes: int,
) -> tuple[bytes, str]:
    """Read exactly one YAML input source and enforce its byte limit.

    Raises:
        HTTPException: If the source selection, extension, or size is invalid.
    """
    if file is None and yaml_content is None:
        raise HTTPException(status_code=400, detail="Either 'file' or 'yaml_content' must be provided")
    if file is not None and yaml_content is not None:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'yaml_content', not both")
    if file is not None:
        filename = file.filename or "schedule.yaml"
        if not filename.lower().endswith((".yaml", ".yml")):
            raise HTTPException(status_code=400, detail="The uploaded file must be YAML")
        content = await file.read(max_bytes + 1)
        input_name = filename
    else:
        assert yaml_content is not None
        content = yaml_content.encode("utf-8")
        input_name = f"nurse-scheduling-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.yaml"
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Scheduling YAML is too large")
    return content, input_name


def _client_id(request: Request, response: Response) -> str:
    """Return a valid client cookie ID, creating a replacement when needed."""
    raw_client_id = request.cookies.get(CLIENT_ID_COOKIE_NAME)
    try:
        client_id = UUID(raw_client_id).hex if raw_client_id is not None else None
    except ValueError:
        client_id = None
    if client_id is None:
        client_id = uuid4().hex
        response.set_cookie(
            key=CLIENT_ID_COOKIE_NAME,
            value=client_id,
            max_age=CLIENT_ID_COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
    return client_id


@router.post("/optimize", status_code=202, response_model=JobResponse)
async def create_job(
    request: Request,
    response: Response,
    file: UploadFile | None = File(None, description="YAML file with scheduling data"),  # noqa: B008
    yaml_content: str | None = Form(None, description="YAML content as a string"),
    prettify: bool | None = Form(None),
    timeout: int | None = Form(None),
    solver: str = Form("ortools/cp-sat", description=scheduler.SOLVER_SELECTOR_HELP),
):
    """Validate an optimization request and enqueue a durable job."""
    settings = _settings(request)
    content, input_name = await _read_input(file, yaml_content, settings.max_yaml_bytes)
    timeout_seconds = timeout if timeout is not None else settings.default_timeout_seconds
    if timeout_seconds <= 0 or timeout_seconds > settings.max_timeout_seconds:
        raise HTTPException(
            status_code=400,
            detail=f"Optimization timeout must be between 1 and {settings.max_timeout_seconds} seconds",
        )
    # Unlike the synchronous endpoints below, create_job must remain async for
    # upload reading. Offload its synchronous controller/store write so it cannot
    # block the ASGI event loop.
    job = await run_in_threadpool(
        _controller(request).create_job,
        input_name=input_name,
        client_id=_client_id(request, response),
        solver=solver,
        prettify=prettify,
        timeout_seconds=timeout_seconds,
        input_bytes=content,
    )
    response.headers["Location"] = f"/optimize/{job.id}"
    response.headers["Retry-After"] = "1"
    return JobResponse.from_job(job)


@router.get("/optimize/{job_id}", response_model=JobResponse)
def get_job(request: Request, job_id: str):
    """Return the current job representation."""
    return JobResponse.from_job(_controller(request).get_job(job_id))


@router.get("/optimize/{job_id}/events")
def stream_events(request: Request, job_id: str, last_event_id: str | None = Header(None)):
    """Replay and stream job events after the client's last event ID.

    Disconnecting closes only this response stream; the durable job continues.
    """
    controller = _controller(request)
    controller.get_job(job_id)

    def generate():
        """Yield SSE frames, blocking up to the configured keepalive interval."""
        for event in controller.stream_events(
            job_id,
            after_id=last_event_id,
            keepalive_seconds=_settings(request).sse_keepalive_seconds,
        ):
            if event is None:
                yield ": keepalive\n\n"
                continue
            if event.type == "job.state_changed":
                job = controller.get_job(job_id)
                event_state = JobState(str(event.data["state"]))
                supports_finish_now = solver_supports_finish_now(job.request.solver)
                cancel_requested = bool(event.data.get("cancel_requested", False))
                early_completion_requested = bool(event.data.get("early_completion_requested", False))
                event = replace(
                    event,
                    data={
                        **event.data,
                        "terminal": event_state.terminal,
                        "controls": {
                            "cancellable": not event_state.terminal and not cancel_requested,
                            "early_completion_available": event_state == JobState.RUNNING
                            and supports_finish_now
                            and not early_completion_requested,
                        },
                    },
                )
            yield format_sse_event(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/optimize/{job_id}/cancel", status_code=202, response_model=JobResponse)
def cancel_job(request: Request, job_id: str):
    """Cancel a queued job or request cancellation of a running job."""
    return JobResponse.from_job(_controller(request).cancel_job(job_id))


@router.post("/optimize/{job_id}/finish-now", status_code=202, response_model=JobResponse)
def finish_job_now(request: Request, job_id: str):
    """Ask a supported running solver to return its current result."""
    return JobResponse.from_job(_controller(request).request_early_completion(job_id))


@router.get("/optimize/{job_id}/xlsx")
def download_xlsx(request: Request, job_id: str):
    """Download the XLSX artifact produced by a completed job."""
    job = _controller(request).get_job(job_id)
    artifact = _controller(request).get_artifact(job_id, job.artifact_name or "schedule.xlsx")
    headers = {"Content-Disposition": f'attachment; filename="{artifact.name}"'}
    return StreamingResponse(BytesIO(artifact.content), media_type=artifact.media_type, headers=headers)


@router.delete("/optimize/{job_id}", status_code=204)
def delete_job(request: Request, job_id: str):
    """Delete a terminal job and all associated retained data."""
    _controller(request).delete_job(job_id)
    return Response(status_code=204)
