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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Literal
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
from .agent_session import (
    ProposalValidationError,
    SessionRuntime,
    _question_log_preview,
    configure_request_logging,
    request_logger,
)
from .config import AiSettings, validate_ai_auth_credentials
from .history import ChatHistory, stop_maintenance
from .lifecycle import SessionTurns
from .optimizer import (
    HttpOptimizerBackend,
    OptimizerArtifact,
    OptimizerBackend,
    OptimizerResultUnavailable,
    SessionOptimizer,
)
from .provider import (
    OpenAiCompatibleProvider,
    ToolCapableChatProvider,
)
from .recovery import SessionRecovery
from .sandbox import SandboxFactory, managed_sandbox_factory
from .sandbox.factory import create_sandbox_factory
from .session_event_stream import SessionEventBroker
from .sessions import SessionStore
from .turns import TurnJournal
from .workspace import (
    SandboxAttachment,
)

SERVICE_NAME = "nurse-scheduling-ai-api"
API_VERSION = "0.2.0"
OWNER_COOKIE = "nurse_scheduling_ai_owner"
ORIGIN_REGEX = (
    r"^(http://(localhost|127\.0\.0\.1|host\.docker\.internal|10(?:\.[0-9]{1,3}){3}|"
    r"192\.168(?:\.[0-9]{1,3}){2}|172\.(1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}):[0-9]+|"
    r"https://([a-zA-Z0-9-]+\.)?nursescheduling\.org)$"
)
logger = logging.getLogger("nurse_scheduling.ai")


class ProposalResponse(BaseModel):
    """The approved schedule the browser should apply."""

    schedule_yaml: str
    history_saved: bool
    """Whether recovery storage saved the approval. It is already applied in the live session."""


class ProposalRejectionResponse(BaseModel):
    """The outcome of a rejection, which is already applied in the live session."""

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


class ChatRequest(BaseModel):
    """One user question for an existing schedule chat."""

    message: str = Field(min_length=1, max_length=100_000)
    message_id: str | None = Field(default=None, min_length=1, max_length=100)
    last_event_id: int = Field(default=0, ge=0)


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


def _sse_event(event_type: str, data: dict[str, object]) -> str:
    """Serialize one server-sent event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


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
            file_values = form.getlist("files")
            if not file_values:
                raise HTTPException(status_code=422, detail="Upload at least one file.")
            return await _read_files(file_values, settings)
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
    store = SessionStore(settings)
    event_broker = SessionEventBroker(max_sessions=settings.max_sessions, max_snapshot_bytes=settings.max_session_bytes)
    turn_journal = TurnJournal(history_log, settings.max_session_bytes)
    turns = SessionTurns()
    recovery = SessionRecovery(store, history_log, event_broker, turn_journal)
    concurrency_limit = asyncio.Semaphore(settings.max_concurrent_requests)
    auth_registry = create_auth_registry(settings.auth_token, settings.auth_tokens)
    require_auth = create_auth_dependency(auth_registry)

    async def restore_session(request: Request, owner: str | None = Cookie(default=None, alias=OWNER_COOKIE)) -> None:
        session_id = request.path_params.get("session_id")
        if session_id is not None:
            await recovery.restore_session(session_id, owner)

    def refresh_owner_cookie(response: Response, owner: str) -> None:
        """Keep browser ownership available for the session's sliding lifetime."""
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
        session = store._sessions.get(session_id)
        if session is None:
            return
        turn = turns.start(
            session_id,
            lambda turn: session.run(runtime, turn, prompt, background=True, artifact=artifact),
            background=True,
        )
        turn.task.add_done_callback(recovery.pin_session(session_id))
        await turn.wait()

    async def optimizer_updated(session_id: str, update: dict[str, object]) -> None:
        await event_broker.emit(
            session_id,
            "optimization_progress" if "progress" in update else "optimization",
            update,
        )

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

    runtime = SessionRuntime(
        settings, store, turns, recovery, provider, sandbox_factory, session_optimizer, concurrency_limit
    )

    def retire_session(session_id: str) -> None:
        """Release everything keyed by a session once the store drops it."""
        turns.retire(session_id)
        session_optimizer.forget_session(session_id)
        recovery.forget_session(session_id)

    store.on_retire(retire_session)
    if history_log is not None:
        store.allow_eviction(
            lambda session_id: (
                recovery.evictable(session_id)
                and not turns.busy(session_id)
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
                    # Interrupted turns stay running in storage. Join their cleanup before sandbox teardown.
                    recovery.shutting_down = True
                    await turns.close()
                    await session_optimizer.close()
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
    app.state.turns = turns
    app.state.provider = provider
    app.state.sandbox_factory = sandbox_factory
    app.state.app_version = app_version
    app.state.session_optimizer = session_optimizer
    app.state.session_event_broker = event_broker
    app.state.turn_journal = turn_journal
    app.state.recovery = recovery
    app.state.runtime = runtime

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
        dependencies=[Depends(require_auth), Depends(restore_session)],
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
        # The client never learns this ID unless the save succeeds, so release its slot otherwise.
        saved = False
        try:
            saved = await recovery.save_session(session.id, http_request.state.auth_credential_id)
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
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> StreamingResponse:
        """Replay and stream assistant turns triggered by background work."""
        store.require_owned(session_id, owner)
        raw_cursor = request.headers.get("last-event-id", "0")
        try:
            after_id = max(0, int(raw_cursor))
        except ValueError:
            raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer.") from None

        async def generate_session_events():
            async for event in event_broker.stream(session_id, after_id):
                if event is None:
                    yield ": keepalive\n\n"
                else:
                    yield f"id: {event.id}\n{_sse_event(event.type, event.data)}"

        return StreamingResponse(
            generate_session_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post(
        "/sessions/{session_id}/stop",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_auth), Depends(restore_session)],
    )
    async def stop_active_turn(
        session_id: str,
        body: StopChatRequest | None = None,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Cancel the named foreground turn, or every assistant turn active in the session."""
        store.require_owned(session_id, owner)
        if body is not None:
            try:
                await turn_journal.request_stop(session_id, body.message_id)
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
            turns.stop(session_id, body.message_id)
            return Response(status_code=status.HTTP_202_ACCEPTED)
        turns.stop(session_id)
        return Response(status_code=status.HTTP_202_ACCEPTED)
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
    ):
        """Retain source files for later messages and return their metadata."""
        store.require_owned(session_id, owner)
        uploads = await _parse_upload_request(request, settings)
        retained = store.retain_uploads(session_id, owner, uploads)
        refresh_owner_cookie(response, owner)
        return [_upload_metadata(item) for item in retained]

    @app.get("/sessions/{session_id}/uploads", dependencies=[Depends(require_auth), Depends(restore_session)])
    async def list_uploads(session_id: str, owner: str | None = Cookie(default=None, alias=OWNER_COOKIE)):
        """List source-file metadata without returning file contents."""
        store.require_owned(session_id, owner)
        return [_upload_metadata(item) for item in store.attachments(session_id)]

    @app.delete(
        "/sessions/{session_id}/uploads/{upload_id}",
        dependencies=[Depends(require_auth), Depends(restore_session)],
        status_code=204,
    )
    async def remove_upload(
        session_id: str,
        upload_id: str,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Remove one retained source file from the session."""
        store.remove_upload(session_id, owner, upload_id)
        refresh_owner_cookie(response, owner)
        response.status_code = 204
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
        dependencies=[Depends(require_auth), Depends(restore_session)],
        status_code=204,
    )
    async def remove_generated_zip(
        session_id: str,
        download_id: str,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Remove one generated ZIP from the owning session."""
        store.remove_download(session_id, owner, download_id)
        refresh_owner_cookie(response, owner)
        response.status_code = 204
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
        """Queue a follow-up for the next boundary in an active agent turn."""
        message = _validate_question(request.message, settings)
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

    def turn_response(turn, cursor: int, owner: str, snapshot: bool = False) -> StreamingResponse:
        async def events():
            async for event in turn.stream(cursor, snapshot=snapshot):
                if event is None:
                    yield ": keepalive\n\n"
                else:
                    event_id, event_type, data = event
                    yield f"id: {event_id}\n{_sse_event(event_type, data)}"

        response = StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
        refresh_owner_cookie(response, owner)
        return response

    @app.post("/sessions/{session_id}/messages", dependencies=[Depends(require_auth), Depends(restore_session)])
    async def stream_message(
        session_id: str,
        body: ChatRequest,
        request: Request,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> StreamingResponse:
        """Stream one answer and retain only text after successful completion."""
        question = _validate_question(body.message, settings)
        session = store.get_owned(session_id, owner)
        replay_turn, replayed = await session.accept_message(
            question, body.message_id, owner, request.state.auth_credential_id, runtime
        )
        return turn_response(replay_turn, body.last_event_id, owner, snapshot=replayed)

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
        # A retry repeats the same update, so the browser can resend it until it is saved.
        if not await recovery.save_session(session_id):
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
            schedule_yaml = store.approve_proposal(session_id, owner, request.base_sha256)
        except ProposalValidationError:
            logger.error("Approved proposal failed revalidation session_id=%s", session_id)
            await recovery.save_session(session_id)
            raise
        # The proposal is gone once adopted, so a failed save is reported rather than refused.
        history_saved = await recovery.save_session(session_id)
        refresh_owner_cookie(response, owner)
        return ProposalResponse(schedule_yaml=schedule_yaml, history_saved=history_saved)

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
        history_saved = await recovery.save_session(session_id)
        refresh_owner_cookie(response, owner)
        return ProposalRejectionResponse(history_saved=history_saved)

    return app
