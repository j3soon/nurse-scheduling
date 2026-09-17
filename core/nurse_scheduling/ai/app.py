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
import base64
import hashlib
import json
import logging
import sys
import threading
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import PurePath
from typing import Literal
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from ..sentry import init_sentry
from ..server.auth import AUTH_SCHEME, create_auth_dependency, create_auth_registry
from .agent import AgentProposal, AgentReasoning, AgentSteering, AgentText, AgentToolStart, AgentToolUse
from .config import AiSettings, validate_ai_auth_credentials
from .documents import DocumentExtractionLimits, DocumentLimitError, InvalidDocumentError, extract_document_text
from .history import ChatHistory, stop_maintenance
from .optimizer import HttpOptimizerBackend, OptimizerBackend, OptimizerResultUnavailable, SessionOptimizer
from .provider import (
    ChatContent,
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
SUPPORTED_IMAGE_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")
SUPPORTED_DOCUMENT_MEDIA_TYPES = {
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain"),
    ".csv": ("text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"),
    ".pdf": ("application/pdf",),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
}
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


class ImageAttachmentCapability(BaseModel):
    """Public limits for the optional image input feature."""

    enabled: bool
    accepted_media_types: tuple[str, ...]
    max_files: int
    max_bytes_per_file: int


class DocumentAttachmentCapability(BaseModel):
    """Public limits for documents converted to text by the backend."""

    enabled: bool
    accepted_extensions: tuple[str, ...]
    max_files: int
    max_bytes_per_file: int


class OptimizerCapability(BaseModel):
    """Whether this deployment can run optimization for the assistant."""

    enabled: bool
    max_runs_per_session: int


class CapabilitiesResponse(BaseModel):
    """Enabled experimental features and their public limits."""

    image_attachments: ImageAttachmentCapability
    document_attachments: DocumentAttachmentCapability
    optimizer: OptimizerCapability
    auth: dict[str, bool | str]


@dataclass(frozen=True)
class ImageAttachment:
    """One validated image kept only for the active provider request."""

    media_type: str
    data: bytes


@dataclass(frozen=True)
class DocumentAttachment:
    """One validated document kept only for the active provider request."""

    filename: str
    media_type: str
    text: str


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so a stale proposal cannot be applied."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


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

    def begin_background(self, session_id: str) -> tuple[list[ChatMessage], str, str, str, str] | None:
        """Reserve an idle session for a trusted background-triggered turn."""
        with self._lock:
            self._prune_expired()
            session = self._sessions.get(session_id)
            if session is None or session.active:
                return None
            session.active = True
            session.accepting_steering = False
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            return (
                list(session.history),
                session.schedule_yaml,
                session.revision,
                session.proposal_yaml,
                session.proposal_diff,
            )

    def require_owned(self, session_id: str, owner_token: str | None) -> None:
        """Validate access to a session without exposing its state."""
        with self._lock:
            self._get_owned(session_id, owner_token)

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


@dataclass(frozen=True)
class SessionEvent:
    """One replayable event from an assistant turn initiated by background work."""

    id: int
    type: str
    data: dict[str, object]


class SessionEventBroker:
    """Process-local replay and notification for background assistant turns."""

    def __init__(self, max_events_per_session: int = 200, max_sessions: int = 1000) -> None:
        self._max_events_per_session = max_events_per_session
        self._max_sessions = max_sessions
        self._events: dict[str, list[SessionEvent]] = {}
        self._signals: dict[str, asyncio.Event] = {}

    def publish(self, session_id: str, event_type: str, data: dict[str, object]) -> None:
        if session_id not in self._events and len(self._events) >= self._max_sessions:
            oldest_session_id = next(iter(self._events))
            self._events.pop(oldest_session_id, None)
            self._signals.pop(oldest_session_id, None)
        events = self._events.setdefault(session_id, [])
        event_id = events[-1].id + 1 if events else 1
        events.append(SessionEvent(event_id, event_type, data))
        del events[: -self._max_events_per_session]
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Return retained events after a cursor for replay and diagnostics."""
        return tuple(event for event in self._events.get(session_id, ()) if event.id > after_id)

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        while True:
            pending = self.events_after(session_id, after_id)
            if pending:
                for event in pending:
                    after_id = event.id
                    yield event
                continue
            signal = self._signals.setdefault(session_id, asyncio.Event())
            signal.clear()
            try:
                await asyncio.wait_for(signal.wait(), timeout=15)
            except TimeoutError:
                yield None


def _sse_event(event_type: str, data: dict[str, object]) -> str:
    """Serialize one server-sent event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# Upload MIME types are client-declared. Narrow signature checks avoid adding an image-decoder dependency.
def _sniff_image_media_type(data: bytes) -> str | None:
    """Sniff a supported media type from file signatures without decoding."""
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        return "image/png"
    if len(data) >= 4 and data.startswith(b"\xff\xd8\xff") and b"\xff\xd9" in data[3:]:
        return "image/jpeg"
    if (
        len(data) >= 12
        and data.startswith(b"RIFF")
        and data[8:12] == b"WEBP"
        and int.from_bytes(data[4:8], "little") + 8 == len(data)
    ):
        return "image/webp"
    return None


async def _read_images(uploads: list[UploadFile], settings: AiSettings) -> list[ImageAttachment]:
    """Read bounded image uploads and verify their declared and actual types."""
    if not uploads:
        return []
    if settings.attachment_mode != "images":
        raise HTTPException(status_code=422, detail="Image attachments are disabled.")
    if len(uploads) > settings.max_image_files:
        raise HTTPException(status_code=413, detail="Too many image attachments.")

    images: list[ImageAttachment] = []
    for upload in uploads:
        declared_type = (upload.content_type or "").lower()
        if declared_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported image type.")
        data = await upload.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise HTTPException(status_code=413, detail="Image attachment is too large.")
        detected_type = _sniff_image_media_type(data)
        if detected_type is None or detected_type != declared_type:
            raise HTTPException(status_code=415, detail="Image content does not match its type.")
        images.append(ImageAttachment(media_type=detected_type, data=data))
    return images


async def _read_documents(
    uploads: list[UploadFile],
    settings: AiSettings,
    concurrency_limit: asyncio.Semaphore,
) -> list[DocumentAttachment]:
    """Read bounded documents, verify their types, and extract prompt text."""
    if not uploads:
        return []
    if settings.document_attachment_mode != "text":
        raise HTTPException(status_code=422, detail="Document attachments are disabled.")
    if len(uploads) > settings.max_document_files:
        raise HTTPException(status_code=413, detail="Too many document attachments.")

    limits = DocumentExtractionLimits(
        max_text_chars=settings.max_document_text_chars,
        max_pdf_pages=settings.max_pdf_pages,
        max_xlsx_sheets=settings.max_xlsx_sheets,
        max_xlsx_cells=settings.max_xlsx_cells,
        max_xlsx_uncompressed_bytes=settings.max_xlsx_uncompressed_bytes,
    )
    documents: list[DocumentAttachment] = []
    for upload in uploads:
        filename = upload.filename or ""
        extension = PurePath(filename).suffix.lower()
        accepted_types = SUPPORTED_DOCUMENT_MEDIA_TYPES.get(extension)
        if accepted_types is None:
            raise HTTPException(status_code=415, detail="Unsupported document type.")
        declared_type = (upload.content_type or "").partition(";")[0].strip().lower()
        if declared_type not in accepted_types:
            raise HTTPException(status_code=415, detail="Document type does not match its filename.")
        data = await upload.read(settings.max_document_bytes + 1)
        if len(data) > settings.max_document_bytes:
            raise HTTPException(status_code=413, detail="Document attachment is too large.")
        try:
            async with concurrency_limit:
                text = await asyncio.to_thread(extract_document_text, filename, data, limits)
        except DocumentLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except InvalidDocumentError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        documents.append(DocumentAttachment(filename=filename, media_type=declared_type, text=text))
    return documents


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
    concurrency_limit: asyncio.Semaphore,
) -> tuple[str, list[ImageAttachment], list[DocumentAttachment]]:
    """Accept the original JSON request or multipart input with attachments."""
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="Request body is not valid JSON.") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Request body must be an object.")
        return _validate_question(body.get("message"), settings), [], []

    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Use JSON or multipart form data.")

    content_length = request.headers.get("content-length")
    max_body_bytes = (
        settings.max_image_files * settings.max_image_bytes
        + settings.max_document_files * settings.max_document_bytes
        + 100_000
        + 65_536
    )
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                raise HTTPException(status_code=413, detail="Attachment request is too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from None

    async with request.form(
        max_files=settings.max_image_files + settings.max_document_files,
        max_fields=1,
        max_part_size=100_000,
    ) as form:
        if any(key not in {"message", "images", "documents"} for key in form):
            raise HTTPException(status_code=422, detail="Unexpected multipart field.")
        message_values = form.getlist("message")
        if len(message_values) != 1 or not isinstance(message_values[0], str):
            raise HTTPException(status_code=422, detail="Multipart request requires one message field.")
        image_values = form.getlist("images")
        document_values = form.getlist("documents")
        if any(not isinstance(value, UploadFile) for value in image_values):
            raise HTTPException(status_code=422, detail="Images must be uploaded as files.")
        if any(not isinstance(value, UploadFile) for value in document_values):
            raise HTTPException(status_code=422, detail="Documents must be uploaded as files.")
        question = _validate_question(message_values[0], settings)
        images = await _read_images(image_values, settings)
        documents = await _read_documents(document_values, settings, concurrency_limit)
    return question, images, documents


def build_provider_messages(
    history: list[ChatMessage],
    schedule_yaml: str,
    question: str,
    images: list[ImageAttachment],
    documents: list[DocumentAttachment],
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
    text_content = question
    if documents:
        document_data = json.dumps(
            [
                {"filename": document.filename, "media_type": document.media_type, "content": document.text}
                for document in documents
            ],
            ensure_ascii=False,
        )
        text_content = f"{question}\n\nAttached untrusted text documents as JSON data:\n{document_data}"
    user_content: ChatContent = text_content
    if images:
        user_content = [{"type": "text", "text": text_content}]
        user_content.extend(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.media_type};base64,{base64.b64encode(image.data).decode('ascii')}"},
            }
            for image in images
        )
    return [
        ChatMessage(role="system", content=system_content),
        *history,
        ChatMessage(role="user", content=user_content),
    ]


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
    turn_locks: dict[str, asyncio.Lock] = {}
    active_turn_tasks: dict[str, asyncio.Task[object]] = {}
    concurrency_limit = asyncio.Semaphore(settings.max_concurrent_requests)
    auth_registry = create_auth_registry(settings.auth_token, settings.auth_tokens)
    require_auth = create_auth_dependency(auth_registry)

    @asynccontextmanager
    async def track_active_turn(session_id: str) -> AsyncIterator[None]:
        task = asyncio.current_task()
        if task is not None:
            active_turn_tasks[session_id] = task
        try:
            yield
        finally:
            if task is not None and active_turn_tasks.get(session_id) is task:
                del active_turn_tasks[session_id]

    if optimizer_backend is None and settings.optimizer_base_url:
        optimizer_backend = HttpOptimizerBackend(
            settings.optimizer_base_url,
            settings.optimizer_auth_token,
            settings.optimizer_request_timeout_seconds,
            settings.optimizer_max_result_bytes,
        )

    async def optimizer_completed(session_id: str, prompt: str) -> None:
        await run_background_turn(session_id, prompt)

    async def optimizer_updated(session_id: str, update: dict[str, object]) -> None:
        event_broker.publish(session_id, "optimization", update)

    session_optimizer = (
        SessionOptimizer(
            optimizer_backend,
            poll_interval_seconds=settings.optimizer_poll_interval_seconds,
            on_completion=optimizer_completed,
            on_update=optimizer_updated,
            max_sessions=settings.max_sessions,
            max_runs_per_session=settings.optimizer_max_runs_per_session,
            max_cached_result_bytes=settings.optimizer_result_cache_bytes,
        )
        if optimizer_backend is not None
        else None
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
            if session_optimizer is not None:
                await session_optimizer.close()
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
            image_attachments=ImageAttachmentCapability(
                enabled=settings.attachment_mode == "images",
                accepted_media_types=SUPPORTED_IMAGE_MEDIA_TYPES,
                max_files=settings.max_image_files,
                max_bytes_per_file=settings.max_image_bytes,
            ),
            document_attachments=DocumentAttachmentCapability(
                enabled=settings.document_attachment_mode == "text",
                accepted_extensions=tuple(SUPPORTED_DOCUMENT_MEDIA_TYPES),
                max_files=settings.max_document_files,
                max_bytes_per_file=settings.max_document_bytes,
            ),
            optimizer=OptimizerCapability(
                enabled=session_optimizer is not None,
                max_runs_per_session=settings.optimizer_max_runs_per_session,
            ),
            auth={"required": auth_registry.enabled, "scheme": AUTH_SCHEME},
        )

    async def run_background_turn(session_id: str, question: str) -> None:
        """Wake an idle agent after a background optimizer job reaches a terminal state."""
        turn_lock = turn_locks.setdefault(session_id, asyncio.Lock())
        async with turn_lock, track_active_turn(session_id):
            snapshot = store.begin_background(session_id)
            if snapshot is None:
                return
            history, schedule_yaml, base_revision, proposal_yaml, proposal_diff = snapshot
            turn_id = str(uuid4())
            event_broker.publish(session_id, "turn_start", {"message_id": turn_id, "trigger": "optimizer"})
            if history_log is not None:
                logged = await history_log.write(
                    "start_turn",
                    turn_id,
                    session_id,
                    None,
                    question,
                    settings.provider_model,
                    0,
                    0,
                )
                if not logged:
                    store.abort(session_id)
                    event_broker.publish(
                        session_id,
                        "error",
                        {"message": "AI chat history is unavailable, so the optimizer result was not reviewed."},
                    )
                    return
            messages = build_provider_messages(
                history,
                schedule_yaml,
                question,
                [],
                [],
                system_prompt=SANDBOX_SYSTEM_PROMPT,
                pending_proposal=bool(proposal_yaml),
            )
            assistant_parts: list[str] = []
            pending_proposal: AgentProposal | None = None
            completed = False
            outcome = "failed"
            error_code: str | None = "internal_error"
            usage: TokenUsage | None = None
            try:
                async with concurrency_limit:
                    agent_events = run_sandbox_agent(
                        provider,
                        sandbox_factory,
                        schedule_yaml,
                        messages,
                        SandboxAgentLimits.from_settings(settings),
                        pending_proposal_yaml=proposal_yaml,
                        pending_proposal_diff=proposal_diff,
                        execute_optimizer=(
                            lambda current_yaml, arguments: session_optimizer.execute(
                                session_id, current_yaml, arguments
                            )
                        )
                        if session_optimizer is not None
                        else None,
                    )
                    async for event in agent_events:
                        if isinstance(event, AgentText):
                            assistant_parts.append(event.text)
                            event_broker.publish(session_id, "delta", {"text": event.text})
                        elif isinstance(event, AgentReasoning):
                            event_broker.publish(session_id, "reasoning", {"text": event.text})
                        elif isinstance(event, TokenUsage):
                            usage = event if usage is None else usage + event
                        elif isinstance(event, AgentToolStart):
                            event_broker.publish(
                                session_id,
                                "tool_start",
                                {"name": event.name, "arguments": event.arguments},
                            )
                        elif isinstance(event, AgentToolUse):
                            event_broker.publish(
                                session_id,
                                "tool",
                                {
                                    "name": event.name,
                                    "arguments": event.arguments,
                                    "result": event.result,
                                    "ok": event.ok,
                                },
                            )
                        elif isinstance(event, AgentScheduleChange):
                            event_broker.publish(
                                session_id,
                                "schedule_change",
                                {"schedule_yaml": event.schedule_yaml},
                            )
                        elif isinstance(event, AgentProposal):
                            pending_proposal = event
                proposal = None
                if pending_proposal is not None:
                    proposal = (pending_proposal.text, pending_proposal.diff)
                completion = store.finish(
                    session_id,
                    question,
                    "".join(assistant_parts),
                    proposal,
                    base_revision=base_revision,
                )
                completed = True
                if not completion.turn_saved:
                    outcome, error_code = "stale", None
                    event_broker.publish(session_id, "stale", {"message": STALE_TURN_ERROR})
                    return
                outcome, error_code = "completed", None
                if completion.proposal_saved and pending_proposal is not None:
                    event_broker.publish(session_id, "proposal", {"diff": pending_proposal.diff})
                event_broker.publish(session_id, "done", {"message_id": turn_id})
            except asyncio.CancelledError:
                outcome, error_code = "cancelled", None
                event_broker.publish(session_id, "stopped", {"message_id": turn_id})
                raise
            except ProviderError:
                error_code = "provider_error"
                event_broker.publish(session_id, "error", {"message": PROVIDER_ERROR})
            except SandboxTurnTimeoutError:
                error_code = "sandbox_timeout"
                event_broker.publish(session_id, "error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})
            except SandboxCandidateError:
                error_code = "candidate_validation"
                event_broker.publish(session_id, "error", {"message": CANDIDATE_VALIDATION_ERROR})
            except SandboxError:
                error_code = "sandbox_error"
                logger.exception("Background AI sandbox turn failed session_id=%s", session_id)
                event_broker.publish(
                    session_id,
                    "error",
                    {"message": "The temporary AI sandbox failed while reviewing optimizer results."},
                )
            except Exception:
                logger.exception("Unexpected background AI turn failure session_id=%s", session_id)
                event_broker.publish(
                    session_id,
                    "error",
                    {"message": "The AI could not review the optimizer result."},
                )
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
        if owner is None:
            owner = str(uuid4())
            response.set_cookie(
                OWNER_COOKIE,
                owner,
                httponly=True,
                secure=settings.cookie_secure,
                # Public deployments allow approved cross-site frontends. Browsers
                # require Secure whenever SameSite=None is used.
                samesite="none" if settings.cookie_secure else "strict",
                max_age=settings.session_ttl_seconds,
            )
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
        """Cancel the foreground or background assistant turn active in a session."""
        store.require_owned(session_id, owner)
        task = active_turn_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
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
        if session_optimizer is None:
            raise HTTPException(status_code=404, detail="Optimizer result not found.")
        try:
            artifact = await session_optimizer.result_artifact(session_id, job_id)
        except OptimizerResultUnavailable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
        )

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
        return Response(status_code=status.HTTP_202_ACCEPTED)

    @app.post("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
    async def stream_message(
        session_id: str,
        request: Request,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> StreamingResponse:
        """Stream one answer and retain only text after successful completion."""
        question, images, documents = await _parse_message_request(request, settings, concurrency_limit)
        turn_lock = turn_locks.setdefault(session_id, asyncio.Lock())
        if turn_lock.locked():
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        await turn_lock.acquire()
        turn_released = False

        def release_turn() -> None:
            nonlocal turn_released
            if not turn_released:
                turn_released = True
                turn_lock.release()

        try:
            history, schedule_yaml, base_revision, proposal_yaml, proposal_diff = store.begin(session_id, owner)
        except BaseException:
            release_turn()
            raise
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
                    len(images),
                    len(documents),
                )
                if not logged:
                    raise HTTPException(status_code=503, detail="AI chat history is temporarily unavailable.")
            except BaseException:
                store.abort(session_id)
                release_turn()
                raise
        request_logger.info(
            "AI request started session_id=%s question_chars=%s images=%s documents=%s question=%s",
            session_id,
            len(question),
            len(images),
            len(documents),
            json.dumps(_question_log_preview(question), ensure_ascii=False),
        )
        stream_started = threading.Event()
        messages = build_provider_messages(
            history,
            schedule_yaml,
            question,
            images,
            documents,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            pending_proposal=bool(proposal_yaml),
        )
        history_question = question
        if images:
            history_question = f"{question}\n[Images were attached to this message.]"
        if documents:
            filenames = json.dumps([document.filename for document in documents], ensure_ascii=False)
            history_question = f"{history_question}\n[Documents were attached: {filenames}.]"

        async def generate_events():
            stream_started.set()
            current_task = asyncio.current_task()
            if current_task is not None:
                active_turn_tasks[session_id] = current_task
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
                        execute_optimizer=(
                            lambda current_yaml, arguments: session_optimizer.execute(
                                session_id, current_yaml, arguments
                            )
                        )
                        if session_optimizer is not None
                        else None,
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
                if current_task is not None and active_turn_tasks.get(session_id) is current_task:
                    del active_turn_tasks[session_id]
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
                release_turn()

        async def abort_unstarted_stream() -> None:
            if not stream_started.is_set():
                store.abort(session_id)
                if history_log is not None:
                    await history_log.write("finish_turn", turn_id, "", "cancelled", None, None)
                release_turn()

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(abort_unstarted_stream),
        )

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
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/sessions/{session_id}/proposal/approve",
        response_model=ProposalResponse,
        dependencies=[Depends(require_auth)],
    )
    async def approve_proposal(
        session_id: str,
        request: ApproveProposalRequest,
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
        return ProposalResponse(schedule_yaml=store.adopt_proposal(session_id, owner, request.base_sha256))

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
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app
