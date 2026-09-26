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
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Literal
from uuid import UUID, uuid4

import anyio
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..sentry import init_sentry
from ..server.auth import AUTH_SCHEME, create_auth_dependency, create_auth_registry
from .agent_session import SessionRuntime
from .config import AiSettings, validate_ai_auth_credentials
from .history import ChatHistory, stop_maintenance
from .lifecycle import AgentRun, RunEvents, SessionRuns
from .optimizer import (
    HttpOptimizerBackend,
    OptimizerArtifact,
    OptimizerBackend,
    OptimizerResultUnavailable,
    SessionOptimizer,
)
from .provider import OpenAiCompatibleProvider, ToolCapableChatProvider
from .sandbox import SandboxFactory, managed_sandbox_factory
from .sandbox.factory import create_sandbox_factory
from .session_events import SessionEventBroker
from .sessions import SessionStore, schedule_revision
from .transcript import ProposalDecision
from .validation import new_schedule_issues, validate_frontend_schedule_yaml
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


class CapabilitiesResponse(BaseModel):
    """Enabled experimental features and their public limits."""

    file_attachments: FileAttachmentCapability
    session_retention_seconds: int
    auth: dict[str, bool | str]


def owner_cookie_token(owner: str | None) -> str:
    """Return a canonical browser owner token or replace an invalid value."""
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
    if not uploads:
        return []
    if len(uploads) > settings.max_attachment_files:
        raise HTTPException(status_code=413, detail="Too many file attachments.")

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
    """Validate one question consistently across JSON and multipart requests."""
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


# FastAPI cannot declaratively combine a JSON body with multipart files on one route.
# Ref: https://fastapi.tiangolo.com/tutorial/request-files/#what-is-form-data
async def _parse_message_request(
    request: Request,
    settings: AiSettings,
) -> tuple[str, list[SandboxAttachment]]:
    """Accept a JSON question or multipart input with arbitrary files."""
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="Request body is not valid JSON.") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Request body must be an object.")
        return _validate_question(body.get("message"), settings), []

    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Use JSON or multipart form data.")

    content_length = request.headers.get("content-length")
    max_body_bytes = settings.max_attachment_files * settings.max_attachment_bytes + 100_000 + 65_536
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                raise HTTPException(status_code=413, detail="Attachment request is too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from None

    try:
        async with request.form(
            max_files=settings.max_attachment_files,
            max_fields=1,
            max_part_size=100_000,
        ) as form:
            if any(key not in {"message", "files"} for key in form):
                raise HTTPException(status_code=422, detail="Unexpected multipart field.")
            message_values = form.getlist("message")
            if len(message_values) != 1 or not isinstance(message_values[0], str):
                raise HTTPException(status_code=422, detail="Multipart request requires one message field.")
            file_values = form.getlist("files")
            if any(not isinstance(value, UploadFile) for value in file_values):
                raise HTTPException(status_code=422, detail="Attachments must be uploaded as files.")
            question = _validate_question(message_values[0], settings)
            files = await _read_files(file_values, settings)
    except StarletteHTTPException as exc:
        if exc.status_code == 400 and str(exc.detail).startswith("Too many files"):
            raise HTTPException(status_code=413, detail="Too many file attachments.") from exc
        raise
    return question, files


class RunResponse(StreamingResponse):
    """The response owns cancellation even if ASGI never iterates its body."""

    def __init__(self, *args, run: AgentRun, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.run = run

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.run.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.shield(self.run.done)


def create_app(
    *,
    settings: AiSettings | None = None,
    provider: ToolCapableChatProvider | None = None,
    sandbox_factory: SandboxFactory | None = None,
    optimizer_backend: OptimizerBackend | None = None,
) -> FastAPI:
    """Construct the independently deployable AI application."""
    init_sentry(API_VERSION, app="ai-backend")
    settings = settings or AiSettings.from_env()
    auth_token, auth_tokens = validate_ai_auth_credentials(
        settings.auth_token,
        settings.auth_tokens,
        required=settings.auth_required,
    )
    settings = replace(settings, auth_token=auth_token, auth_tokens=auth_tokens)
    configure_request_logging(settings.request_log_enabled)
    provider = provider or OpenAiCompatibleProvider(settings, include_usage=bool(settings.history_postgres_url))
    history_log = (
        ChatHistory(settings.history_postgres_url, settings.history_retention_days)
        if settings.history_postgres_url
        else None
    )
    if sandbox_factory is None:
        sandbox_factory = create_sandbox_factory(settings)
    store = SessionStore(settings)
    event_broker = SessionEventBroker(max_sessions=settings.max_sessions)
    runs = SessionRuns()
    concurrency_limit = asyncio.Semaphore(settings.max_concurrent_requests)
    auth_registry = create_auth_registry(settings.auth_token, settings.auth_tokens)
    require_auth = create_auth_dependency(auth_registry)

    def refresh_owner_cookie(response: Response, owner: str) -> None:
        """Keep browser ownership available for the session's sliding lifetime."""
        try:
            canonical_owner = str(UUID(owner))
        except ValueError:
            return
        response.set_cookie(
            OWNER_COOKIE,
            canonical_owner,
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
        async def emit(event_type: str, data: dict[str, object]) -> None:
            # Retirement revokes publication as well as cancelling execution.
            if store.get(session_id) is not None:
                event_broker.publish(session_id, event_type, data)

        session = store.get(session_id)
        if session is None:
            return
        run = runs.start(
            session_id,
            lambda run: session.run(
                run,
                prompt,
                runtime=runtime,
                emit=emit,
                background=True,
                artifact=artifact,
            ),
            background=True,
        )
        try:
            await run.wait()
        finally:
            run.cancel()

    async def optimizer_updated(session_id: str, update: dict[str, object]) -> None:
        event_broker.publish(
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
        settings, store, concurrency_limit, history_log, provider, sandbox_factory, session_optimizer
    )

    def retire_session(session_id: str) -> None:
        """Release everything keyed by a session once the store drops it."""
        runs.stop(session_id)
        session_optimizer.forget_session(session_id)
        event_broker.forget_session(session_id)

    store.on_retire(retire_session)

    async def record_decision(run_id: str | None, decision: ProposalDecision) -> None:
        """Log a decision on the run that proposed it. It already took effect, so a failed write only logs."""
        if history_log is not None and run_id is not None:
            await history_log.write("record_decision", run_id, decision)

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
                    # Drain runs while their sandbox factory is still available.
                    await runs.close()
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
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    app.state.settings = settings
    app.state.auth_registry = auth_registry
    app.state.session_store = store
    app.state.runs = runs
    app.state.provider = provider
    app.state.sandbox_factory = sandbox_factory
    app.state.session_optimizer = session_optimizer
    app.state.session_event_broker = event_broker

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
        """Create a process-local chat session for the calling browser."""
        if len(request.schedule_yaml.encode("utf-8")) > settings.max_schedule_bytes:
            raise HTTPException(status_code=413, detail="Schedule is too large.")
        owner = owner_cookie_token(owner)
        refresh_owner_cookie(response, owner)
        session = store.create(owner, request.schedule_yaml)
        logger.info(
            "Created AI session session_id=%s auth_credential_id=%s",
            session.id,
            http_request.state.auth_credential_id,
        )
        return CreateSessionResponse(id=session.id)

    @app.get("/sessions/{session_id}/events", dependencies=[Depends(require_auth)])
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
        dependencies=[Depends(require_auth)],
    )
    async def stop_active_turn(
        session_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Cancel the foreground or background assistant run active in a session."""
        store.require_owned(session_id, owner)
        runs.stop(session_id)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    @app.get(
        "/sessions/{session_id}/optimizations/{job_id}/xlsx",
        dependencies=[Depends(require_auth)],
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
        dependencies=[Depends(require_auth)],
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
        dependencies=[Depends(require_auth)],
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

    @app.post("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
    async def stream_message(
        session_id: str,
        request: Request,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> StreamingResponse:
        """Stream one answer and retain only text after successful completion."""
        question, attachments = await _parse_message_request(request, settings)
        session = store.require_owned(session_id, owner)
        events = RunEvents()
        run = runs.start(
            session_id,
            lambda run: session.run(
                run,
                question,
                runtime=runtime,
                emit=events.emit,
                owner=owner,
                credential_id=request.state.auth_credential_id,
                attachments=attachments,
            ),
        )
        try:
            if not await asyncio.shield(run.ready):
                await run.wait()
        except BaseException:
            run.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.shield(run.done)
            raise
        request_logger.info(
            "AI request started session_id=%s question_chars=%s question=%s files=%s",
            session_id,
            len(question),
            json.dumps(_question_log_preview(question), ensure_ascii=False),
            len(attachments),
        )

        async def generate_events():
            run.streaming.set()
            async for event_type, data in events.stream(run):
                yield _sse_event(event_type, data)

        response = RunResponse(
            generate_events(),
            run=run,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        refresh_owner_cookie(response, owner)
        return response

    @app.put(
        "/sessions/{session_id}/schedule",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_auth)],
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
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        refresh_owner_cookie(response, owner)
        return response

    @app.post(
        "/sessions/{session_id}/proposal/approve",
        response_model=ProposalResponse,
        dependencies=[Depends(require_auth)],
    )
    async def approve_proposal(
        session_id: str,
        request: ApproveProposalRequest,
        response: Response,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> ProposalResponse:
        """Return the proposed schedule once the browser proves it holds the base revision."""
        # Revalidate before adopting, so a refused proposal never becomes the
        # session schedule that later turns are hydrated from.
        approved, replaced = store.peek_proposal(session_id, owner, request.base_sha256)
        validation = validate_frontend_schedule_yaml(approved, settings.max_schedule_bytes)
        if not validation.valid:
            # A user can approve while their schedule is still incomplete, so only
            # a problem this proposal introduces blocks it.
            replaced_validation = validate_frontend_schedule_yaml(replaced, settings.max_schedule_bytes)
            if new_schedule_issues(replaced_validation, validation):
                logger.error("Approved proposal failed revalidation session_id=%s", session_id)
                await record_decision(store.discard_proposal(session_id, owner, "invalid"), "invalid")
                raise HTTPException(status_code=409, detail="The proposed schedule is no longer valid.")
        schedule_yaml, run_id = store.adopt_proposal(session_id, owner, request.base_sha256)
        await record_decision(run_id, "approved")
        refresh_owner_cookie(response, owner)
        return ProposalResponse(schedule_yaml=schedule_yaml)

    @app.post(
        "/sessions/{session_id}/proposal/reject",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_auth)],
    )
    async def reject_proposal(
        session_id: str,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> Response:
        """Drop the pending proposal at the user's request."""
        await record_decision(store.discard_proposal(session_id, owner), "rejected")
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        refresh_owner_cookie(response, owner)
        return response

    return app
