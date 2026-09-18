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
import hashlib
import json
import logging
import math
import sys
import threading
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..sentry import init_sentry
from ..server.auth import AUTH_SCHEME, create_auth_dependency, create_auth_registry
from .agent import AgentProposal, AgentReasoning, AgentSteering, AgentText, AgentToolStart, AgentToolUse
from .config import AiSettings, validate_ai_auth_credentials
from .history import ChatHistory, stop_maintenance
from .provider import (
    ChatMessage,
    OpenAiCompatibleProvider,
    ProviderError,
    TokenUsage,
    ToolCapableChatProvider,
)
from .sandbox import SandboxError, SandboxFactory, managed_sandbox_factory
from .sandbox.factory import create_sandbox_factory
from .sandbox_agent import (
    SANDBOX_SYSTEM_PROMPT,
    AgentScheduleChange,
    SandboxAgentLimits,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxTurnTimeoutError,
    run_sandbox_agent,
)
from .schedule_context import describe_schedule
from .validation import new_schedule_issues, validate_frontend_schedule_yaml

SERVICE_NAME = "nurse-scheduling-ai-api"
API_VERSION = "0.2.0"
OWNER_COOKIE = "nurse_scheduling_ai_owner"
PROPOSAL_APPROVED_HISTORY = (
    "The user approved the previous schedule proposal. Its changes are now part of the current canonical schedule."
)
PROPOSAL_REJECTED_HISTORY = (
    "The user rejected the previous schedule proposal. All schedule changes made during that agent turn were "
    "discarded. This turn starts with a fresh workspace containing the current canonical schedule."
)
PROPOSAL_INVALID_HISTORY = (
    "The previous schedule proposal failed trusted validation when the user approved it, so it was discarded. All "
    "schedule changes made during that agent turn were dropped. This turn starts with a fresh workspace containing "
    "the current canonical schedule."
)
CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent turn were "
    "discarded. The canonical schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_TURN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_TURN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
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


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so a stale proposal cannot be applied."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


def owner_cookie_token(owner: str | None) -> str:
    """Return a canonical browser owner token or replace an invalid value."""
    if owner is not None:
        try:
            return str(UUID(owner))
        except ValueError:
            pass
    return str(uuid4())


@dataclass
class ChatSession:
    """Process-local conversation state owned by one browser cookie."""

    id: str
    owner_token: str
    expires_at: float
    schedule_yaml: str
    revision: str
    history: list[ChatMessage] = field(default_factory=list)
    active: bool = False
    accepting_steering: bool = False
    steering_queue: list[tuple[str, str]] = field(default_factory=list)
    steering_ids: set[str] = field(default_factory=set)
    proposal_yaml: str = ""
    proposal_diff: str = ""


@dataclass(frozen=True)
class TurnCompletion:
    """Whether a completed turn and its optional proposal were retained."""

    turn_saved: bool
    proposal_saved: bool


class SessionStore:
    """Bounded in-memory session storage for the first experimental slice."""

    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.RLock()

    def create(self, owner_token: str, schedule_yaml: str) -> ChatSession:
        """Create a session after pruning expired entries."""
        with self._lock:
            self._prune_expired()
            if len(self._sessions) >= self._settings.max_sessions:
                raise HTTPException(status_code=429, detail="The AI service has reached its session limit.")
            session = ChatSession(
                id=str(uuid4()),
                owner_token=owner_token,
                expires_at=time.monotonic() + self._settings.session_ttl_seconds,
                schedule_yaml=schedule_yaml,
                revision=schedule_revision(schedule_yaml),
            )
            self._sessions[session.id] = session
            return session

    def begin(self, session_id: str, owner_token: str | None) -> tuple[list[ChatMessage], str, str, str, str]:
        """Reserve a session and return its history and schedule snapshots."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            if session.active:
                raise HTTPException(status_code=409, detail="This chat session already has an active response.")
            session.active = True
            session.accepting_steering = True
            session.steering_queue.clear()
            session.steering_ids.clear()
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            return (
                list(session.history),
                session.schedule_yaml,
                session.revision,
                session.proposal_yaml,
                session.proposal_diff,
            )

    def status(self, session_id: str, owner_token: str | None) -> int:
        """Return the remaining lifetime without extending the session."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            return max(1, math.ceil(session.expires_at - time.monotonic()))

    def finish(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        proposal: tuple[str, str] | None = None,
        *,
        base_revision: str,
        turn_messages: Sequence[ChatMessage] = (),
    ) -> TurnCompletion:
        """Save a completed turn when its schedule revision is still current."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return TurnCompletion(turn_saved=False, proposal_saved=False)
            if session.revision != base_revision:
                session.active = False
                session.accepting_steering = False
                session.steering_queue.clear()
                session.steering_ids.clear()
                return TurnCompletion(turn_saved=False, proposal_saved=False)
            session.history.extend(
                turn_messages
                or (
                    ChatMessage(role="user", content=user_message),
                    ChatMessage(role="assistant", content=assistant_message),
                )
            )
            session.history = session.history[-self._settings.max_history_messages :]
            proposal_saved = proposal is not None
            if proposal_saved:
                session.proposal_yaml, session.proposal_diff = proposal
            session.active = False
            session.accepting_steering = False
            session.steering_queue.clear()
            session.steering_ids.clear()
            return TurnCompletion(turn_saved=True, proposal_saved=proposal_saved)

    def queue_steering(
        self,
        session_id: str,
        owner_token: str | None,
        message_id: str,
        message: str,
    ) -> None:
        """Queue a message for the next model boundary of an active response."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            if not session.active or not session.accepting_steering:
                raise HTTPException(status_code=409, detail="The active response is no longer accepting messages.")
            if message_id in session.steering_ids:
                return
            # Counted over the whole turn, not the drained queue, because the seen-ID set
            # that makes a retried POST idempotent is never emptied mid-turn.
            if len(session.steering_ids) >= self._settings.max_history_messages:
                raise HTTPException(status_code=429, detail="Too many messages are already queued.")
            session.steering_queue.append((message_id, message))
            session.steering_ids.add(message_id)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]:
        """Drain queued messages and close the final race when a response is done."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.active:
                return []
            queued = list(session.steering_queue)
            session.steering_queue.clear()
            if close_if_empty and not queued:
                session.accepting_steering = False
            return queued

    def update_schedule(self, session_id: str, owner_token: str | None, schedule_yaml: str) -> None:
        """Replace the schedule snapshot, which drops any proposal made against the old one."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            if session.schedule_yaml == schedule_yaml:
                return
            session.schedule_yaml = schedule_yaml
            session.revision = schedule_revision(schedule_yaml)
            session.proposal_yaml = ""
            session.proposal_diff = ""
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

    def peek_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> tuple[str, str]:
        """Return the pending proposal and the schedule it would replace, without adopting it."""
        with self._lock:
            session = self._require_approvable(session_id, owner_token, base_sha256)
            return session.proposal_yaml, session.schedule_yaml

    def adopt_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> str:
        """Adopt a revalidated proposal as the session schedule and record the approval."""
        with self._lock:
            session = self._require_approvable(session_id, owner_token, base_sha256)
            approved = session.proposal_yaml
            session.proposal_yaml = ""
            session.proposal_diff = ""
            session.schedule_yaml = approved
            session.revision = schedule_revision(approved)
            self._append_history_event(session, PROPOSAL_APPROVED_HISTORY)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            return approved

    def _require_approvable(self, session_id: str, owner_token: str | None, base_sha256: str) -> ChatSession:
        """Resolve a session whose pending proposal may still be approved by its browser."""
        session = self._get_owned(session_id, owner_token)
        if not session.proposal_yaml:
            raise HTTPException(status_code=404, detail="No proposal is waiting for approval.")
        if session.revision != base_sha256:
            session.proposal_yaml = ""
            session.proposal_diff = ""
            raise HTTPException(
                status_code=409,
                detail="The schedule changed after this proposal was created, so it was discarded.",
            )
        return session

    def discard_proposal(
        self,
        session_id: str,
        owner_token: str | None,
        history_event: str = PROPOSAL_REJECTED_HISTORY,
    ) -> None:
        """Drop a pending proposal and record why it was dropped once."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            had_proposal = bool(session.proposal_yaml)
            session.proposal_yaml = ""
            session.proposal_diff = ""
            if had_proposal:
                self._append_history_event(session, history_event)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

    def abort(self, session_id: str) -> None:
        """Release a session without recording an incomplete response."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.active = False
                session.accepting_steering = False
                session.steering_queue.clear()
                session.steering_ids.clear()

    def _append_history_event(self, session: ChatSession, content: str) -> None:
        """Append one trusted application event within the caller's lock."""
        session.history.append(ChatMessage(role="user", content=content))
        session.history = session.history[-self._settings.max_history_messages :]

    def _get_owned(self, session_id: str, owner_token: str | None) -> ChatSession:
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None or owner_token is None or session.owner_token != owner_token:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        return session

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired_ids = [session_id for session_id, session in self._sessions.items() if session.expires_at <= now]
        for session_id in expired_ids:
            del self._sessions[session_id]


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


def build_provider_messages(
    history: list[ChatMessage],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
) -> list[ChatMessage]:
    """Build a provider prompt that keeps schedule data separate from instructions."""
    system_content = f"{system_prompt}\n\nCurrent schedule summary:\n{describe_schedule(schedule_yaml)}"
    if pending_proposal:
        system_content += (
            "\nA validated proposal is pending. Its exact candidate and diff are available in the trusted workspace "
            "files described above."
        )
    if attachments:
        system_content += (
            f"\nThis turn includes {len(attachments)} untrusted attached file(s). Read "
            "/workspace/attachments/manifest.json before inspecting them."
        )
    return [
        ChatMessage(role="system", content=system_content),
        *history,
        ChatMessage(role="user", content=question),
    ]


def create_app(
    *,
    settings: AiSettings | None = None,
    provider: ToolCapableChatProvider | None = None,
    sandbox_factory: SandboxFactory | None = None,
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

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if history_log is not None and not await history_log.write("initialize"):
            raise RuntimeError("AI history database initialization failed")
        maintenance = asyncio.create_task(history_log.maintain()) if history_log is not None else None
        try:
            async with managed_sandbox_factory(sandbox_factory):
                yield
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
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.settings = settings
    app.state.auth_registry = auth_registry
    app.state.session_store = store
    app.state.provider = provider
    app.state.sandbox_factory = sandbox_factory

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
        history, schedule_yaml, base_revision, proposal_yaml, proposal_diff = store.begin(session_id, owner)
        turn_id = str(uuid4())
        if history_log is not None:
            try:
                logged = await history_log.write(
                    "start_turn",
                    turn_id,
                    session_id,
                    request.state.auth_credential_id,
                    question,
                    settings.provider_model,
                    len(attachments),
                )
                if not logged:
                    raise HTTPException(status_code=503, detail="AI chat history is temporarily unavailable.")
            except BaseException:
                store.abort(session_id)
                raise
        request_logger.info(
            "AI request started session_id=%s question_chars=%s question=%s files=%s",
            session_id,
            len(question),
            json.dumps(_question_log_preview(question), ensure_ascii=False),
            len(attachments),
        )
        stream_started = threading.Event()
        messages = build_provider_messages(
            history,
            schedule_yaml,
            question,
            attachments,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            pending_proposal=bool(proposal_yaml),
        )
        history_question = question
        if attachments:
            filenames = json.dumps([attachment.filename for attachment in attachments], ensure_ascii=False)
            history_question = f"{history_question}\n[Files were attached: {filenames}.]"

        async def generate_events():
            stream_started.set()
            assistant_parts: list[str] = []
            pending_proposal: AgentProposal | None = None
            completed = False
            outcome = "cancelled"
            error_code = None
            usage = None
            turn_messages = [ChatMessage(role="user", content=history_question)]
            assistant_segment: list[str] = []
            try:
                async with concurrency_limit:
                    agent_events = run_sandbox_agent(
                        provider,
                        sandbox_factory,
                        schedule_yaml,
                        messages,
                        SandboxAgentLimits.from_settings(settings),
                        take_steering=lambda close_if_empty: store.take_steering(session_id, close_if_empty),
                        pending_proposal_yaml=proposal_yaml,
                        pending_proposal_diff=proposal_diff,
                        attachments=attachments,
                    )
                    async for event in agent_events:
                        if isinstance(event, AgentText):
                            assistant_parts.append(event.text)
                            assistant_segment.append(event.text)
                            yield _sse_event("delta", {"text": event.text})
                        elif isinstance(event, AgentReasoning):
                            yield _sse_event("reasoning", {"text": event.text})
                        elif isinstance(event, TokenUsage):
                            usage = event if usage is None else usage + event
                        elif isinstance(event, AgentToolStart):
                            yield _sse_event(
                                "tool_start",
                                {
                                    "name": event.name,
                                    "arguments": event.arguments,
                                },
                            )
                        elif isinstance(event, AgentToolUse):
                            yield _sse_event(
                                "tool",
                                {
                                    "name": event.name,
                                    "arguments": event.arguments,
                                    "result": event.result,
                                    "ok": event.ok,
                                },
                            )
                        elif isinstance(event, AgentSteering):
                            if assistant_segment:
                                turn_messages.append(ChatMessage(role="assistant", content="".join(assistant_segment)))
                            turn_messages.append(ChatMessage(role="user", content=event.text))
                            assistant_segment.clear()
                            yield _sse_event(
                                "steering",
                                {
                                    "message_id": event.message_id,
                                    "message": event.text,
                                },
                            )
                        elif isinstance(event, AgentScheduleChange):
                            yield _sse_event(
                                "schedule_change",
                                {"schedule_yaml": event.schedule_yaml},
                            )
                        elif isinstance(event, AgentProposal):
                            pending_proposal = event
                proposal = None
                if pending_proposal is not None:
                    proposal = (pending_proposal.text, pending_proposal.diff)
                turn_messages.append(ChatMessage(role="assistant", content="".join(assistant_segment)))
                completion = store.finish(
                    session_id,
                    history_question,
                    "".join(assistant_parts),
                    proposal,
                    base_revision=base_revision,
                    turn_messages=turn_messages,
                )
                completed = True
                outcome = "completed" if completion.turn_saved else "stale"
                history_saved = None
                if history_log is not None:
                    history_saved = await history_log.write(
                        "finish_turn",
                        turn_id,
                        "".join(assistant_parts),
                        outcome,
                        None,
                        usage,
                    )
                if not completion.turn_saved:
                    yield _sse_event("stale", {"message": STALE_TURN_ERROR})
                    return
                if completion.proposal_saved:
                    yield _sse_event("proposal", {"diff": pending_proposal.diff})
                done = {"message_id": turn_id}
                if history_saved is not None:
                    done["history_saved"] = history_saved
                yield _sse_event("done", done)
            except asyncio.CancelledError:
                raise
            except ProviderError:
                outcome, error_code = "failed", "provider_error"
                yield _sse_event("error", {"message": PROVIDER_ERROR})
            except SandboxTurnTimeoutError:
                outcome, error_code = "failed", "sandbox_timeout"
                yield _sse_event("error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})
            except SandboxCandidateError as exc:
                outcome, error_code = "failed", "candidate_validation"
                logger.warning("AI candidate validation failed: %s", exc)
                yield _sse_event("error", {"message": CANDIDATE_VALIDATION_ERROR})
            except SandboxError:
                outcome, error_code = "failed", "sandbox_error"
                logger.exception("AI sandbox turn failed")
                yield _sse_event("error", {"message": "The temporary AI sandbox failed. Please try again."})
            except Exception:
                outcome, error_code = "failed", "internal_error"
                logger.exception("Unexpected AI stream failure")
                yield _sse_event("error", {"message": "The AI response failed unexpectedly."})
            finally:
                if not completed:
                    store.abort(session_id)
                    if history_log is not None:
                        await history_log.write(
                            "finish_turn",
                            turn_id,
                            "".join(assistant_parts),
                            outcome,
                            error_code,
                            usage,
                        )

        async def abort_unstarted_stream() -> None:
            if not stream_started.is_set():
                store.abort(session_id)
                if history_log is not None:
                    await history_log.write("finish_turn", turn_id, "", "cancelled", None, None)

        response = StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(abort_unstarted_stream),
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
                store.discard_proposal(session_id, owner, PROPOSAL_INVALID_HISTORY)
                raise HTTPException(status_code=409, detail="The proposed schedule is no longer valid.")
        schedule_yaml = store.adopt_proposal(session_id, owner, request.base_sha256)
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
        store.discard_proposal(session_id, owner)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        refresh_owner_cookie(response, owner)
        return response

    return app
