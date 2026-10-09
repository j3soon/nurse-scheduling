"""FastAPI application for schedule chat with optional attachments."""

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

# This code is mostly AI generated.

import asyncio
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import replace
from typing import Literal, cast
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..sentry import SentryClientAddressMiddleware, init_sentry
from ..server.auth import AUTH_SCHEME, create_auth_dependency, create_auth_registry
from ..service_logging import configure_service_logging
from ..version import get_app_version
from .agent_session import AgentSession, SessionRuntime
from .config import AiSettings, validate_ai_auth_credentials
from .history import ChatHistory, stop_maintenance
from .lifecycle import TERMINAL_EVENTS, AgentRun, SessionRuns
from .optimizer import (
    OptimizerArtifact,
    OptimizerBackend,
    OptimizerResultUnavailable,
    SessionOptimizer,
)
from .optimizer_http import HttpOptimizerBackend
from .provider import OpenAiCompatibleProvider, ToolCapableChatProvider
from .recovery import SessionRecovery
from .sandbox import SandboxFactory, managed_sandbox_factory
from .sandbox.factory import create_sandbox_factory
from .session_event_stream import SessionEventStream, SessionResetData
from .session_events import OptimizerUpdate
from .sessions import SessionStore, schedule_revision
from .workspace import SandboxAttachment

SERVICE_NAME = "nurse-scheduling-ai-api"
__all__ = ("SessionStore", "schedule_revision")
API_VERSION = "0.2.0"
OWNER_COOKIE = "nurse_scheduling_ai_owner"
ORIGIN_REGEX = (
    r"^(http://(localhost|127\.0\.0\.1|host\.docker\.internal|10(?:\.[0-9]{1,3}){3}|"
    r"192\.168(?:\.[0-9]{1,3}){2}|172\.(1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}):[0-9]+|"
    r"https://([a-zA-Z0-9-]+\.)?nursescheduling\.org)$"
)
logger = logging.getLogger("nurse_scheduling.ai")
request_logger = logging.getLogger("nurse_scheduling.ai.requests")


def configure_request_logging(enabled: bool) -> None:
    """Route question previews to stdout by default without seizing the logger.

    The previews carry chat text, so a deployment must be able to silence or redirect
    them. An operator's own handler wins, and `AI_REQUEST_LOG_ENABLED=false` turns the
    previews off without losing the rest of this logger's records.
    """
    if not enabled:
        request_logger.setLevel(logging.WARNING)
        return
    request_logger.setLevel(logging.INFO)
    if request_logger.handlers or logging.getLogger().handlers:
        return
    request_handler = logging.StreamHandler(sys.stdout)
    request_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    request_logger.addHandler(request_handler)


QUESTION_LOG_PREVIEW_CHARS = 200


def _question_log_preview(question: str) -> str:
    """Return a compact, single-line question preview for request logs."""
    preview = " ".join(question.split())
    if len(preview) > QUESTION_LOG_PREVIEW_CHARS:
        return f"{preview[: QUESTION_LOG_PREVIEW_CHARS - 3]}..."
    return preview


class ProposalResponse(BaseModel):
    """The approved schedule the browser should apply."""

    schedule_yaml: str
    history_saved: bool


class ProposalRejectionResponse(BaseModel):
    """Whether recovery storage saved the rejection, which already took effect."""

    history_saved: bool


class ApproveProposalRequest(BaseModel):
    """The revision the browser holds when it approves a proposal."""

    base_sha256: str = Field(min_length=64, max_length=64)


class UpdateScheduleRequest(BaseModel):
    """A newer schedule snapshot for an existing session."""

    schedule_yaml: str = Field(min_length=1)


class CreateSessionResponse(BaseModel):
    """Public identifier for a newly created chat session."""

    id: str


class SessionStatusResponse(BaseModel):
    """Remaining lifetime for one browser-owned chat session."""

    expires_in_seconds: int


class CreateSessionRequest(BaseModel):
    """The schedule snapshot owned by a new chat session."""

    schedule_yaml: str = Field(min_length=1)
    frontend_version: str | None = Field(default=None, min_length=1, max_length=200)


class ChatRequest(BaseModel):
    """One user question for an existing schedule chat."""

    message: str = Field(min_length=1, max_length=100_000)
    # A repeated client message ID reattaches to its run instead of asking again.
    message_id: str | None = Field(default=None, min_length=1, max_length=100)
    frontend_version: str | None = Field(default=None, min_length=1, max_length=200)


class StopChatRequest(BaseModel):
    """Identify a question that may still be arriving at the server."""

    message_id: str = Field(min_length=1, max_length=100)


class QueueChatRequest(ChatRequest):
    """One user message queued while the assistant is working."""

    message_id: str = Field(min_length=1, max_length=100)


class HealthResponse(BaseModel):
    """Stable service identity returned by health endpoints."""

    status: Literal["ok"] = "ok"
    service_name: str = SERVICE_NAME
    api_version: str = API_VERSION


class FileAttachmentCapability(BaseModel):
    """Public limits for arbitrary files copied into the sandbox."""

    enabled: bool
    max_files: int
    max_bytes_per_file: int
    retained: bool = True


class CapabilitiesResponse(BaseModel):
    """Enabled experimental features and their public limits."""

    app_version: str
    file_attachments: FileAttachmentCapability
    session_retention_seconds: int
    auth: dict[str, bool | str]


def owner_cookie_token(owner: str | None) -> str:
    """Return a normalized browser owner token or replace an invalid value."""
    if owner is not None:
        try:
            return str(UUID(owner))
        except ValueError:
            pass
    return str(uuid4())


async def _session_sse(
    session: AgentSession, after_id: int, *, until_run: AgentRun | None = None, force_reset: bool = False
) -> AsyncIterator[str]:
    """Frame the shared replay journal. A compatibility reader ends with its own run."""
    async with aclosing(session.events(after_id, force_reset=force_reset)) as reader:
        async for event in reader:
            if event is None:
                yield ": keepalive\n\n"
                continue
            data = event.data
            reset = cast(SessionResetData, data) if event.type == "session_reset" else None
            if reset is not None:
                data = {
                    **data,
                    "proposal_diff": session.pending_proposal.diff if session.pending_proposal else "",
                    "active_run_id": session.snapshot.run_id if session.snapshot else None,
                }
            yield f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(data)}\n\n"
            if until_run is not None and (
                (data.get("run_id") == until_run.id and event.type in TERMINAL_EVENTS)
                or (
                    reset is not None
                    and (
                        until_run.done.done()
                        or any(
                            item["type"] in TERMINAL_EVENTS and item["data"].get("run_id") == until_run.id
                            for item in reset["events"]
                        )
                    )
                )
            ):
                return


async def _read_files(uploads: list[UploadFile], settings: AiSettings) -> list[SandboxAttachment]:
    """Read arbitrary bounded files without interpreting or executing them."""
    attachments = []
    for index, upload in enumerate(uploads, start=1):
        data = await upload.read(settings.max_attachment_bytes + 1)
        if len(data) > settings.max_attachment_bytes:
            raise HTTPException(status_code=413, detail="File attachment is too large.")
        filename = upload.filename or f"attachment-{index}"
        declared_type = (upload.content_type or "application/octet-stream").partition(";")[0].strip().lower()
        attachments.append(SandboxAttachment(filename, declared_type or "application/octet-stream", data))
    return attachments


def _validate_question(raw_message: object, settings: AiSettings) -> str:
    """Validate one question consistently across message and steering requests."""
    try:
        request = ChatRequest.model_validate({"message": raw_message})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Message is invalid.") from exc
    question = request.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message must not be blank.")
    if len(question) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail="Message is too large.")
    return question


async def _parse_upload_request(request: Request, settings: AiSettings) -> list[SandboxAttachment]:
    """Accept multipart input with one or more arbitrary files and no other fields."""
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Upload files as multipart form data.")

    content_length = request.headers.get("content-length")
    max_body_bytes = settings.max_attachment_files * settings.max_attachment_bytes + 65_536
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                raise HTTPException(status_code=413, detail="Attachment request is too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from None

    try:
        async with request.form(max_files=settings.max_attachment_files, max_fields=0) as form:
            if any(key != "files" for key in form):
                raise HTTPException(status_code=422, detail="Unexpected multipart field.")
            uploads: list[UploadFile] = []
            for value in form.getlist("files"):
                if not isinstance(value, UploadFile):
                    raise HTTPException(status_code=422, detail="Attachments must be uploaded as files.")
                uploads.append(value)
            if not uploads:
                raise HTTPException(status_code=422, detail="Upload at least one file.")
            return await _read_files(uploads, settings)
    except StarletteHTTPException as exc:
        if exc.status_code == 400 and str(exc.detail).startswith("Too many files"):
            raise HTTPException(status_code=413, detail="Too many file attachments.") from exc
        if exc.status_code == 400 and str(exc.detail).startswith("Too many fields"):
            raise HTTPException(status_code=422, detail="Unexpected multipart field.") from exc
        raise


def _upload_metadata(upload: SandboxAttachment) -> dict[str, str | int]:
    """Describe one retained source file without its contents."""
    return {"id": upload.id, "filename": upload.filename, "media_type": upload.media_type, "bytes": len(upload.data)}


def create_app(
    *,
    settings: AiSettings | None = None,
    provider: ToolCapableChatProvider | None = None,
    sandbox_factory: SandboxFactory | None = None,
    optimizer_backend: OptimizerBackend | None = None,
) -> FastAPI:
    """Construct the independently deployable AI application."""
    app_version = get_app_version()
    init_sentry(app_version, app="ai-backend", api_version=API_VERSION)
    configure_service_logging(logger)
    settings = settings or AiSettings.from_env()
    auth_token, auth_tokens = validate_ai_auth_credentials(
        settings.auth_token,
        settings.auth_tokens,
        required=settings.auth_required,
    )
    settings = replace(settings, auth_token=auth_token, auth_tokens=auth_tokens)
    configure_request_logging(settings.request_log_enabled)
    provider = provider or OpenAiCompatibleProvider(settings, include_usage=True)
    history_log = ChatHistory(settings.history_postgres_url) if settings.history_postgres_url else None
    if sandbox_factory is None:
        sandbox_factory = create_sandbox_factory(settings)
    event_stream = SessionEventStream(max_sessions=settings.max_sessions)
    store = SessionStore(settings, event_stream=event_stream)
    recovery = SessionRecovery(history_log, store, event_stream)
    runs = SessionRuns()
    concurrency_limit = asyncio.Semaphore(settings.max_concurrent_requests)
    auth_registry = create_auth_registry(settings.auth_token, settings.auth_tokens)
    require_auth = create_auth_dependency(auth_registry)

    async def restore_session(request: Request, owner: str | None = Cookie(default=None, alias=OWNER_COOKIE)) -> None:
        """Load a saved session that is not in memory after a restart or eviction."""
        session_id = request.path_params.get("session_id")
        if session_id is None or not recovery.enabled or owner is None or store.get(session_id) is not None:
            return
        await recovery.restore(session_id, owner)

    def refresh_owner_cookie(response: Response, owner: str | None) -> None:
        """Keep browser ownership available for the session's sliding lifetime."""
        if owner is None:
            return
        try:
            normalized_owner = str(UUID(owner))
        except ValueError:
            return
        response.set_cookie(
            OWNER_COOKIE,
            normalized_owner,
            httponly=True,
            secure=settings.cookie_secure,
            # Public deployments allow approved cross-site frontends. Browsers
            # require Secure whenever SameSite=None is used.
            samesite="none" if settings.cookie_secure else "strict",
            max_age=settings.session_ttl_seconds,
        )

    if optimizer_backend is None:
        optimizer_backend = HttpOptimizerBackend(
            settings.optimizer_base_url,
            settings.optimizer_auth_token,
            settings.optimizer_request_timeout_seconds,
            settings.optimizer_max_result_bytes,
        )

    async def optimizer_completed(session_id: str, prompt: str, artifact: OptimizerArtifact | None) -> None:
        session = store.get(session_id)
        if session is None:
            return
        run = runs.start(
            session_id,
            lambda run: session.run(run, prompt, runtime=runtime, background=True, artifact=artifact),
            background=True,
        )
        run.task.add_done_callback(recovery.pin(session_id))
        try:
            await run.wait()
        finally:
            run.cancel()

    async def optimizer_updated(session_id: str, update: OptimizerUpdate) -> None:
        session = store.get(session_id)
        if session is not None:
            session.publish_optimizer_update(update)

    session_optimizer = SessionOptimizer(
        optimizer_backend,
        poll_interval_seconds=settings.optimizer_poll_interval_seconds,
        on_completion=optimizer_completed,
        on_update=optimizer_updated,
        default_timeout_seconds=settings.optimizer_default_timeout_seconds,
        max_sessions=settings.max_sessions,
        max_runs_per_session=settings.optimizer_max_runs_per_session,
        max_result_bytes=settings.optimizer_max_result_bytes,
        max_cached_result_bytes=settings.optimizer_result_cache_bytes,
        max_schedule_bytes=settings.max_schedule_bytes,
    )

    runtime = SessionRuntime(settings, store, concurrency_limit, recovery, provider, sandbox_factory, session_optimizer)

    def retire_session(session_id: str) -> None:
        """Release everything keyed by a session once the store drops it."""
        runs.stop(session_id)
        session_optimizer.forget_session(session_id)
        event_stream.forget_session(session_id)
        recovery.forget(session_id)

    store.on_retire(retire_session)
    if recovery.enabled:
        # A full store unloads idle sessions that storage can restore. Running work stays loaded.
        store.allow_eviction(
            lambda session_id: (
                recovery.evictable(session_id)
                and not runs.busy(session_id)
                and not session_optimizer.has_unfinished_run(session_id)
            )
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        prepare_sandbox = getattr(sandbox_factory, "prepare", None)
        if prepare_sandbox is not None:
            await prepare_sandbox()
        if history_log is not None and not await history_log.write("initialize"):
            raise RuntimeError("AI history database initialization failed")
        maintenance = asyncio.create_task(history_log.maintain()) if history_log is not None else None
        try:
            async with managed_sandbox_factory(sandbox_factory):
                try:
                    yield
                finally:
                    # Drain runs while their sandbox factory is still available. Interrupted
                    # runs stay running in recovery storage, so a restart reports them.
                    await runs.close()
                    await session_optimizer.close()
                    await recovery.close()
        finally:
            if maintenance is not None:
                await stop_maintenance(maintenance)

    generated_docs_are_public = not auth_registry.enabled
    app = FastAPI(
        title="Nurse Scheduling AI API",
        version=API_VERSION,
        lifespan=lifespan,
        openapi_url="/openapi.json" if generated_docs_are_public else None,
        docs_url="/docs" if generated_docs_are_public else None,
        redoc_url="/redoc" if generated_docs_are_public else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    app.state.settings = settings
    app.state.auth_registry = auth_registry
    app.state.session_store = store
    app.state.runs = runs
    app.state.provider = provider
    app.state.sandbox_factory = sandbox_factory
    app.state.app_version = app_version
    app.state.session_optimizer = session_optimizer
    app.state.session_event_stream = event_stream
    app.state.recovery = recovery

    app.add_middleware(SentryClientAddressMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Report schema failures without echoing the input, which can be binary file data."""
        errors = [{key: error[key] for key in ("type", "loc", "msg") if key in error} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Report process health without contacting the model provider."""
        return HealthResponse()

    @app.get("/ready", response_model=HealthResponse)
    async def ready() -> HealthResponse:
        """Report that required startup configuration was accepted."""
        return HealthResponse()

    @app.get("/capabilities", response_model=CapabilitiesResponse)
    async def capabilities() -> CapabilitiesResponse:
        """Report optional features without exposing provider configuration."""
        return CapabilitiesResponse(
            app_version=app.state.app_version,
            file_attachments=FileAttachmentCapability(
                enabled=True,
                max_files=settings.max_attachment_files,
                max_bytes_per_file=settings.max_attachment_bytes,
            ),
            session_retention_seconds=settings.session_ttl_seconds,
            auth={"required": auth_registry.enabled, "scheme": AUTH_SCHEME},
        )

    @app.post(
        "/sessions",
        response_model=CreateSessionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_auth)],
    )
    async def create_session(
        request: CreateSessionRequest,
        http_request: Request,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ):
        """Create a chat session for the calling browser."""
        if len(request.schedule_yaml.encode("utf-8")) > settings.max_schedule_bytes:
            raise HTTPException(status_code=413, detail="Schedule is too large.")
        owner = owner_cookie_token(owner)
        refresh_owner_cookie(response, owner)
        session = store.create(owner, request.schedule_yaml)
        session.observe_frontend_version(request.frontend_version, app.state.app_version)
        # The client never learns this ID unless the save succeeds, so release its slot otherwise.
        saved = False
        try:
            saved = await recovery.save(session.id, http_request.state.auth_credential_id)
        finally:
            if not saved:
                store.discard(session.id)
        if not saved:
            raise HTTPException(status_code=503, detail="AI message recovery is temporarily unavailable.")
        logger.info(
            "Created AI session session_id=%s auth_credential_id=%s",
            session.id,
            http_request.state.auth_credential_id,
        )
        return CreateSessionResponse(id=session.id)

    @app.get("/sessions/{session_id}/events", dependencies=[Depends(require_auth), Depends(restore_session)])
    async def stream_session_events(
        session_id: str,
        request: Request,
        reset: bool = False,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> StreamingResponse:
        """Replay every session event. Disconnect only detaches this reader."""
        session = store.require_owned(session_id, owner)
        raw_cursor = request.headers.get("last-event-id", "0")
        try:
            after_id = max(0, int(raw_cursor))
        except ValueError:
            raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer.") from None

        return StreamingResponse(
            _session_sse(session, after_id, force_reset=reset),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post(
        "/sessions/{session_id}/stop",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def stop_active_run(
        session_id: str,
        body: StopChatRequest | None = None,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Cancel the named message's run, or every assistant run active in the session."""
        session = store.require_owned(session_id, owner)
        await session.stop(None if body is None else body.message_id, runtime=runtime, runs=runs)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    @app.post(
        "/sessions/{session_id}/uploads",
        dependencies=[Depends(require_auth), Depends(restore_session)],
        status_code=status.HTTP_201_CREATED,
    )
    async def add_uploads(
        session_id: str,
        request: Request,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> list[dict[str, str | int]]:
        """Retain source files for later messages and return their metadata."""
        store.require_owned(session_id, owner)
        # Eviction must not unload the session while its upload is read.
        release = recovery.pin(session_id)
        try:
            uploads = await _parse_upload_request(request, settings)
        finally:
            release()
        retained = store.retain_uploads(session_id, owner, uploads)
        refresh_owner_cookie(response, owner)
        return [_upload_metadata(item) for item in retained]

    @app.get("/sessions/{session_id}/uploads", dependencies=[Depends(require_auth), Depends(restore_session)])
    async def list_uploads(
        session_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> list[dict[str, str | int]]:
        """List source-file metadata without returning file contents."""
        return [_upload_metadata(item) for item in store.attachments(session_id, owner)]

    @app.delete(
        "/sessions/{session_id}/uploads/{upload_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def remove_upload(
        session_id: str,
        upload_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Remove one retained source file from the session."""
        store.remove_upload(session_id, owner, upload_id)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        refresh_owner_cookie(response, owner)
        return response

    @app.get(
        "/sessions/{session_id}/downloads/{download_id}", dependencies=[Depends(require_auth), Depends(restore_session)]
    )
    async def download_generated_zip(
        session_id: str,
        download_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Deliver one captured ZIP without exposing arbitrary sandbox paths."""
        return Response(
            content=store.download(session_id, owner, download_id),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="download.zip"'},
        )

    @app.delete(
        "/sessions/{session_id}/downloads/{download_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def remove_generated_zip(
        session_id: str,
        download_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Remove one generated ZIP from the owning session."""
        store.remove_download(session_id, owner, download_id)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        refresh_owner_cookie(response, owner)
        return response

    @app.get(
        "/sessions/{session_id}/optimizations/{job_id}/xlsx",
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def download_optimization(
        session_id: str,
        job_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Download a completed optimizer result without exposing optimizer credentials."""
        store.require_owned(session_id, owner)
        try:
            artifact = await session_optimizer.result_artifact(session_id, job_id)
        except OptimizerResultUnavailable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
        )

    @app.get(
        "/sessions/{session_id}",
        response_model=SessionStatusResponse,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def session_status(
        session_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> SessionStatusResponse:
        """Report whether a stored browser session remains available without extending it."""
        return SessionStatusResponse(expires_in_seconds=store.status(session_id, owner))

    @app.post(
        "/sessions/{session_id}/messages/queue",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def queue_message(
        session_id: str,
        request: QueueChatRequest,
        http_request: Request,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Queue a follow-up for the next boundary in an active agent run."""
        message = _validate_question(request.message, settings)
        session = store.require_owned(session_id, owner)
        session.observe_frontend_version(request.frontend_version, app.state.app_version)
        store.queue_steering(session_id, owner, request.message_id, message)
        request_logger.info(
            "AI steering queued session_id=%s message_chars=%s message=%s auth_credential_id=%s",
            session_id,
            len(message),
            json.dumps(_question_log_preview(message), ensure_ascii=False),
            http_request.state.auth_credential_id,
        )
        response = Response(status_code=status.HTTP_202_ACCEPTED)
        refresh_owner_cookie(response, owner)
        return response

    @app.post("/sessions/{session_id}/messages", dependencies=[Depends(require_auth), Depends(restore_session)])
    async def send_message(
        session_id: str,
        body: ChatRequest,
        request: Request,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Start a run independently of its event subscribers."""
        question = _validate_question(body.message, settings)
        session = store.require_owned(session_id, owner)
        session.observe_frontend_version(body.frontend_version, app.state.app_version)
        cursor = event_stream.cursor(session_id)
        receipt = await session.accept_message(
            question,
            body.message_id,
            runtime=runtime,
            runs=runs,
            owner=owner,
            credential_id=request.state.auth_credential_id,
        )
        run = receipt.run
        if run is not None:
            request_logger.info(
                "AI request started session_id=%s question_chars=%s question=%s files=%s",
                session_id,
                len(question),
                json.dumps(_question_log_preview(question), ensure_ascii=False),
                len(session.uploads),
            )
        # Compatibility readers explicitly request SSE. They use the same journal
        # and cannot cancel execution by leaving. New clients, and a message accepted
        # earlier or stopped before its run began, receive a message acknowledgement.
        if run is not None and "text/event-stream" in request.headers.get("accept", ""):
            response: Response = StreamingResponse(
                _session_sse(session, cursor, until_run=run),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            response = JSONResponse({"run_id": receipt.run_id}, status_code=status.HTTP_202_ACCEPTED)
        refresh_owner_cookie(response, owner)
        return response

    @app.put(
        "/sessions/{session_id}/schedule",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def update_schedule(
        session_id: str,
        request: UpdateScheduleRequest,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Point an existing session at the schedule the browser now holds."""
        if len(request.schedule_yaml.encode("utf-8")) > settings.max_schedule_bytes:
            raise HTTPException(status_code=413, detail="The schedule is too large for the AI service.")
        store.update_schedule(session_id, owner, request.schedule_yaml)
        # A retry repeats the same update, so the browser can send it again until it is saved.
        if not await recovery.save(session_id):
            raise HTTPException(status_code=503, detail="AI message recovery is temporarily unavailable.")
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        refresh_owner_cookie(response, owner)
        return response

    @app.post(
        "/sessions/{session_id}/proposal/approve",
        response_model=ProposalResponse,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def approve_proposal(
        session_id: str,
        request: ApproveProposalRequest,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> ProposalResponse:
        """Return the proposed schedule once the browser proves it holds the base revision."""
        try:
            approved = store.approve_proposal(session_id, owner, request.base_sha256)
        except HTTPException as exc:
            if exc.status_code == 409:
                # A stale revision discards the proposal before refusing approval.
                await recovery.save(session_id)
            raise
        # The decision already took effect, so a failed save is reported rather than refused.
        history_saved = await recovery.save(session_id)
        if approved is None:
            raise HTTPException(status_code=409, detail="The proposed schedule is no longer valid.")
        refresh_owner_cookie(response, owner)
        return ProposalResponse(schedule_yaml=approved, history_saved=history_saved)

    @app.post(
        "/sessions/{session_id}/proposal/reject",
        response_model=ProposalRejectionResponse,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def reject_proposal(
        session_id: str,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> ProposalRejectionResponse:
        """Drop the pending proposal at the user's request."""
        store.discard_proposal(session_id, owner)
        history_saved = await recovery.save(session_id)
        refresh_owner_cookie(response, owner)
        return ProposalRejectionResponse(history_saved=history_saved)

    return app
