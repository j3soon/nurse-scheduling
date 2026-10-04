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
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..sentry import init_sentry
from ..server.auth import AUTH_SCHEME, create_auth_dependency, create_auth_registry
from .agent import AgentProposal, AgentReasoning, AgentSteering, AgentText, AgentToolStart, AgentToolUse
from .background import (
    CANDIDATE_VALIDATION_ERROR,
    PROVIDER_ERROR,
    SANDBOX_COMMAND_TIMEOUT_ERROR,
    SANDBOX_TURN_TIMEOUT_ERROR,
    STALE_TURN_ERROR,
    SessionEventBroker,
    attachment_notes,
    build_provider_messages,
    recent_history,
    run_background_turn,
)
from .config import AiSettings, validate_ai_auth_credentials
from .history import ChatHistory, stop_maintenance
from .optimizer import (
    HttpOptimizerBackend,
    OptimizerArtifact,
    OptimizerBackend,
    OptimizerResultUnavailable,
    SessionOptimizer,
)
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
    AgentDownload,
    AgentScheduleChange,
    SandboxAgentLimits,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxCommandTimeoutError,
    SandboxDownloadError,
    SandboxTurnTimeoutError,
    run_sandbox_agent,
)
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


class MessageChatRequest(ChatRequest):
    """One user question and the IDs of session uploads attached to it."""

    upload_ids: list[str] = Field(default_factory=list)


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
    dropped_history_messages: int = 0
    active: bool = False
    accepting_steering: bool = False
    steering_queue: list[tuple[str, str]] = field(default_factory=list)
    steering_ids: set[str] = field(default_factory=set)
    proposal_yaml: str = ""
    proposal_diff: str = ""
    downloads: dict[str, bytes] = field(default_factory=dict)
    uploads: dict[str, SandboxAttachment] = field(default_factory=dict)


SESSION_MEMORY_LIMIT_MESSAGE = "The AI service has reached its memory limit."


def _text_bytes(value: object) -> int:
    """Return the UTF-8 size of one chat content value, ignoring inline image data."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, list):
        return sum(len(part.get("text", "").encode("utf-8")) for part in value if part.get("type") == "text")
    return 0


def _session_bytes(session: "ChatSession") -> int:
    """Return the text and file bytes one session retains."""
    total = _text_bytes(session.schedule_yaml) + _text_bytes(session.proposal_yaml) + _text_bytes(session.proposal_diff)
    total += sum(_text_bytes(message.get("content")) for message in session.history)
    return (
        total
        + sum(_text_bytes(text) for _message_id, text in session.steering_queue)
        + sum(map(len, session.downloads.values()))
        + sum(len(upload.data) for upload in session.uploads.values())
    )


def _unique_filename(filename: str, taken: set[str]) -> str:
    """Add the lowest free ` (n)` suffix before the extension when a session already has the filename."""
    if filename not in taken:
        return filename
    stem, dot, extension = filename.rpartition(".")
    if not stem:
        stem, dot, extension = filename, "", ""
    counter = 1
    while f"{stem} ({counter}){dot}{extension}" in taken:
        counter += 1
    return f"{stem} ({counter}){dot}{extension}"


@dataclass(frozen=True)
class TurnCompletion:
    """Whether a completed turn and its optional proposal were retained."""

    turn_saved: bool
    proposal_saved: bool
    history_trimmed_count: int = 0


class SessionStore:
    """Bounded in-memory session storage for the first experimental slice."""

    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, ChatSession] = {}
        self._retained_bytes = 0
        self._session_bytes: dict[str, int] = {}
        self._lock = threading.RLock()
        self._on_retire: Callable[[str], None] | None = None

    def on_retire(self, callback: Callable[[str], None]) -> None:
        """Register the cleanup that follows every dropped session."""
        self._on_retire = callback

    @property
    def retained_bytes(self) -> int:
        """Return the text and file bytes retained across live sessions."""
        with self._lock:
            return self._retained_bytes

    def _recount(self, session: ChatSession) -> None:
        """Refresh one session's contribution to the retained total, under the caller's lock."""
        previous = self._session_bytes.get(session.id, 0)
        current = _session_bytes(session)
        self._session_bytes[session.id] = current
        self._retained_bytes += current - previous

    def _charge(self, session: ChatSession, delta: int) -> None:
        """Apply a known size change to one session's contribution, under the caller's lock.

        Cheaper than `_recount`, which re-encodes the whole history while every session
        waits on the lock.
        """
        self._session_bytes[session.id] += delta
        self._retained_bytes += delta

    def _forget(self, session_id: str) -> None:
        """Drop one session's contribution to the retained total, under the caller's lock."""
        self._retained_bytes -= self._session_bytes.pop(session_id, 0)

    def _require_capacity(self, additional_bytes: int) -> None:
        """Refuse content that would push retained session state past the configured budget.

        Checked where a client pushes new text. A completed turn is never refused here,
        because its answer has already streamed to the user; `_trim_history_to_budget`
        reclaims the space instead.

        Raises:
            HTTPException: With status 429 when the budget is exhausted.
        """
        if self._retained_bytes + additional_bytes > self._settings.max_session_bytes:
            raise HTTPException(status_code=429, detail=SESSION_MEMORY_LIMIT_MESSAGE)

    def _trim_history_to_budget(self, session: ChatSession, protected_messages: int) -> None:
        """Drop this session's oldest context until retained text fits the budget.

        A turn grows a session without passing an admission check, so sessions admitted
        cheaply would otherwise accumulate answers and proposals far past the budget and
        hold them until they expire. Older context is the part a later turn needs least,
        and the message cap already truncates from the same end.

        Keep the entire completed turn so its answer still has the question and any
        steering that produced it. Retained text therefore settles at the budget plus
        one turn and any pending proposal per session.
        """
        while self._retained_bytes > self._settings.max_session_bytes:
            oldest_answer = next(
                (index for index, message in enumerate(session.history) if message["role"] == "assistant"),
                None,
            )
            if oldest_answer is None or len(session.history) - oldest_answer - 1 < protected_messages:
                break
            removed = session.history[: oldest_answer + 1]
            del session.history[: oldest_answer + 1]
            self._charge(session, -sum(_text_bytes(message.get("content")) for message in removed))
            session.dropped_history_messages += len(removed)

    def _effective_trimmed_count(self, session: ChatSession) -> int:
        """Count retained-history and prompt-budget omissions visible to a client."""
        return (
            session.dropped_history_messages
            + len(session.history)
            - len(recent_history(session.history, self._settings.max_history_chars))
        )

    def _cap_history(self, session: ChatSession) -> None:
        """Limit retained messages without leaving an assistant reply at the front."""
        overflow = max(0, len(session.history) - max(2, self._settings.max_history_messages))
        if overflow:
            while overflow < len(session.history) and session.history[overflow]["role"] != "user":
                overflow += 1
            del session.history[:overflow]
            session.dropped_history_messages += overflow

    def create(self, owner_token: str, schedule_yaml: str) -> ChatSession:
        """Create a session after pruning expired entries."""
        with self._lock:
            self._prune_expired()
            if len(self._sessions) >= self._settings.max_sessions:
                raise HTTPException(status_code=429, detail="The AI service has reached its session limit.")
            self._require_capacity(_text_bytes(schedule_yaml))
            session = ChatSession(
                id=str(uuid4()),
                owner_token=owner_token,
                expires_at=time.monotonic() + self._settings.session_ttl_seconds,
                schedule_yaml=schedule_yaml,
                revision=schedule_revision(schedule_yaml),
            )
            self._sessions[session.id] = session
            self._recount(session)
            return session

    def begin(self, session_id: str, owner_token: str | None) -> tuple[list[ChatMessage], str, str, str, str, int]:
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
                session.dropped_history_messages,
            )

    def begin_background(self, session_id: str) -> tuple[list[ChatMessage], str, str, str, str, int] | None:
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
                session.dropped_history_messages,
            )

    def require_owned(self, session_id: str, owner_token: str | None) -> None:
        """Validate access to a session without exposing its state."""
        with self._lock:
            self._get_owned(session_id, owner_token)

    def retain_uploads(
        self, session_id: str, owner_token: str | None, uploads: Sequence[SandboxAttachment]
    ) -> tuple[SandboxAttachment, ...]:
        """Retain new uploads between turns without replacing a file a message may reference."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            if session.active:
                raise HTTPException(status_code=409, detail="Wait for the active response before uploading files.")
            if len(session.uploads) + len(uploads) > self._settings.max_attachment_files:
                raise HTTPException(status_code=413, detail="Too many retained files. Remove unused uploads first.")
            delta = sum(len(upload.data) for upload in uploads)
            self._require_capacity(delta)
            filenames = {item.filename for item in session.uploads.values()}
            retained_uploads = []
            for upload in uploads:
                filename = _unique_filename(upload.filename, filenames)
                filenames.add(filename)
                retained_uploads.append(replace(upload, filename=filename, id=str(uuid4())))
            session.uploads.update((item.id, item) for item in retained_uploads)
            self._charge(session, delta)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            return tuple(retained_uploads)

    def attachments(self, session_id: str) -> tuple[SandboxAttachment, ...]:
        """Snapshot retained source files for a foreground or background turn."""
        with self._lock:
            self._prune_expired()
            session = self._sessions.get(session_id)
            return tuple(session.uploads.values()) if session is not None else ()

    def remove_upload(self, session_id: str, owner_token: str | None, upload_id: str) -> None:
        """Remove an unused source file between turns and reclaim its bytes."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            if session.active:
                raise HTTPException(status_code=409, detail="Wait for the active response before removing files.")
            upload = session.uploads.pop(upload_id, None)
            if upload is None:
                raise HTTPException(status_code=404, detail="The uploaded file is no longer available.")
            self._charge(session, -len(upload.data))
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

    def save_download(self, session_id: str, download_id: str, content: bytes) -> bool:
        """Retain a bounded generated ZIP within the existing session memory budget."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or len(content) > self._settings.max_download_bytes:
                return False
            previous = session.downloads.get(download_id, b"")
            delta = len(content) - len(previous)
            if self._retained_bytes + delta > self._settings.max_session_bytes:
                return False
            session.downloads[download_id] = content
            self._charge(session, delta)
            return True

    def download(self, session_id: str, owner_token: str | None, download_id: str) -> bytes:
        """Read a generated ZIP only for its owning browser."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            try:
                return session.downloads[download_id]
            except KeyError:
                raise HTTPException(status_code=404, detail="This generated ZIP is no longer available.") from None

    def has_active_turn(self, session_id: str, owner_token: str | None) -> bool:
        """Check whether Stop has a reserved turn to cancel."""
        with self._lock:
            return self._get_owned(session_id, owner_token).active

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
                self._recount(session)
                return TurnCompletion(turn_saved=False, proposal_saved=False)
            completed_turn = turn_messages or (
                ChatMessage(role="user", content=user_message),
                ChatMessage(role="assistant", content=assistant_message),
            )
            session.history.extend(completed_turn)
            self._cap_history(session)
            proposal_saved = proposal is not None
            if proposal_saved:
                session.proposal_yaml, session.proposal_diff = proposal
            session.active = False
            session.accepting_steering = False
            session.steering_queue.clear()
            session.steering_ids.clear()
            self._recount(session)
            self._trim_history_to_budget(session, min(len(completed_turn), len(session.history)))
            return TurnCompletion(
                turn_saved=True,
                proposal_saved=proposal_saved,
                history_trimmed_count=self._effective_trimmed_count(session),
            )

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
            message_bytes = _text_bytes(message)
            self._require_capacity(message_bytes)
            session.steering_queue.append((message_id, message))
            session.steering_ids.add(message_id)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            self._charge(session, message_bytes)

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
            self._charge(session, -sum(_text_bytes(text) for _message_id, text in queued))
            return queued

    def update_schedule(self, session_id: str, owner_token: str | None, schedule_yaml: str) -> None:
        """Replace the schedule snapshot, which drops any proposal made against the old one."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            if session.schedule_yaml == schedule_yaml:
                return
            # The replacement also drops the proposal made against the old schedule, so an
            # update that frees more than it adds is never refused.
            additional_bytes = (
                _text_bytes(schedule_yaml)
                - _text_bytes(session.schedule_yaml)
                - _text_bytes(session.proposal_yaml)
                - _text_bytes(session.proposal_diff)
            )
            if additional_bytes > 0:
                self._require_capacity(additional_bytes)
            session.schedule_yaml = schedule_yaml
            session.revision = schedule_revision(schedule_yaml)
            session.proposal_yaml = ""
            session.proposal_diff = ""
            self._recount(session)

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
            self._recount(session)
            return approved

    def _require_approvable(self, session_id: str, owner_token: str | None, base_sha256: str) -> ChatSession:
        """Resolve a session whose pending proposal may still be approved by its browser."""
        session = self._get_owned(session_id, owner_token)
        if not session.proposal_yaml:
            raise HTTPException(status_code=404, detail="No proposal is waiting for approval.")
        if session.revision != base_sha256:
            session.proposal_yaml = ""
            session.proposal_diff = ""
            self._recount(session)
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
            self._recount(session)

    def abort(self, session_id: str) -> None:
        """Release a session without recording an incomplete response."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.active = False
                session.accepting_steering = False
                session.steering_queue.clear()
                session.steering_ids.clear()
                self._recount(session)

    def _append_history_event(self, session: ChatSession, content: str) -> None:
        """Append one trusted application event within the caller's lock."""
        session.history.append(ChatMessage(role="user", content=content))
        self._cap_history(session)

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
            self._forget(session_id)
            if self._on_retire is not None:
                self._on_retire(session_id)


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
    background_turn_tasks: dict[str, set[asyncio.Task[object]]] = {}
    pending_turn_stops: set[str] = set()
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
    async def track_active_turn(session_id: str) -> AsyncIterator[None]:
        task = asyncio.current_task()
        if task is not None:
            active_turn_tasks[session_id] = task
        try:
            yield
        finally:
            if task is not None and active_turn_tasks.get(session_id) is task:
                del active_turn_tasks[session_id]

    if optimizer_backend is None:
        optimizer_backend = HttpOptimizerBackend(
            settings.optimizer_base_url,
            settings.optimizer_auth_token,
            settings.optimizer_request_timeout_seconds,
            settings.optimizer_max_result_bytes,
        )

    async def optimizer_completed(session_id: str, prompt: str, artifact: OptimizerArtifact | None) -> None:
        task = asyncio.current_task()
        if task is not None:
            background_turn_tasks.setdefault(session_id, set()).add(task)
        try:
            await run_background_turn(
                session_id,
                prompt,
                artifact,
                settings=settings,
                store=store,
                event_broker=event_broker,
                turn_locks=turn_locks,
                track_active_turn=track_active_turn,
                concurrency_limit=concurrency_limit,
                history_log=history_log,
                provider=provider,
                sandbox_factory=sandbox_factory,
                session_optimizer=session_optimizer,
            )
        finally:
            if task is not None:
                tasks = background_turn_tasks[session_id]
                tasks.discard(task)
                if not tasks:
                    del background_turn_tasks[session_id]

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

    def retire_session(session_id: str) -> None:
        """Release everything keyed by a session once the store drops it."""
        turn_locks.pop(session_id, None)
        pending_turn_stops.discard(session_id)
        session_optimizer.forget_session(session_id)
        event_broker.forget_session(session_id)

    store.on_retire(retire_session)

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
                yield
        finally:
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
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    app.state.settings = settings
    app.state.auth_registry = auth_registry
    app.state.session_store = store
    app.state.turn_locks = turn_locks
    app.state.provider = provider
    app.state.sandbox_factory = sandbox_factory
    app.state.session_optimizer = session_optimizer
    app.state.session_event_broker = event_broker

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
        """Cancel the foreground or background assistant turn active in a session."""
        store.require_owned(session_id, owner)
        task = active_turn_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
        elif store.has_active_turn(session_id, owner):
            pending_turn_stops.add(session_id)
        for background_task in tuple(background_turn_tasks.get(session_id, ())):
            if not background_task.done():
                background_task.cancel()
        return Response(status_code=status.HTTP_202_ACCEPTED)

    @app.post(
        "/sessions/{session_id}/uploads",
        dependencies=[Depends(require_auth)],
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

    @app.get("/sessions/{session_id}/uploads", dependencies=[Depends(require_auth)])
    async def list_uploads(session_id: str, owner: str | None = Cookie(default=None, alias=OWNER_COOKIE)):
        """List source-file metadata without returning file contents."""
        store.require_owned(session_id, owner)
        return [_upload_metadata(item) for item in store.attachments(session_id)]

    @app.delete("/sessions/{session_id}/uploads/{upload_id}", dependencies=[Depends(require_auth)], status_code=204)
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

    @app.get("/sessions/{session_id}/downloads/{download_id}", dependencies=[Depends(require_auth)])
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
        body: MessageChatRequest,
        request: Request,
        owner: str | None = Cookie(default=None, alias=OWNER_COOKIE),
    ) -> StreamingResponse:
        """Stream one answer and retain only text after successful completion."""
        question = _validate_question(body.message, settings)
        upload_ids = list(dict.fromkeys(body.upload_ids))
        store.require_owned(session_id, owner)
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
            history, schedule_yaml, base_revision, proposal_yaml, proposal_diff, previously_dropped = store.begin(
                session_id, owner
            )
            # Uploads cannot change while the turn is active, so this snapshot stays valid for the whole turn.
            hydrated_attachments = store.attachments(session_id)
            if not set(upload_ids) <= {item.id for item in hydrated_attachments}:
                store.abort(session_id)
                raise HTTPException(status_code=422, detail="An attached file is no longer available.")
        except BaseException:
            pending_turn_stops.discard(session_id)
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
                    len(upload_ids),
                )
                if not logged:
                    raise HTTPException(status_code=503, detail="AI chat history is temporarily unavailable.")
            except BaseException:
                store.abort(session_id)
                pending_turn_stops.discard(session_id)
                release_turn()
                raise
        request_logger.info(
            "AI request started session_id=%s question_chars=%s question=%s files=%s",
            session_id,
            len(question),
            json.dumps(_question_log_preview(question), ensure_ascii=False),
            len(upload_ids),
        )
        stream_started = threading.Event()
        latest_artifact = await session_optimizer.latest_result_artifact(session_id)
        retained_history = recent_history(history, settings.max_history_chars)
        dropped_history = previously_dropped + len(history) - len(retained_history)
        messages = build_provider_messages(
            retained_history,
            schedule_yaml,
            question,
            hydrated_attachments,
            new_upload_ids=upload_ids,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            pending_proposal=bool(proposal_yaml),
            optimizer_result_available=latest_artifact is not None,
            max_history_chars=settings.max_history_chars,
            max_download_bytes=settings.max_download_bytes,
        )
        # Later turns list retained files again, so history keeps only the files this message attached.
        history_question = question + attachment_notes(hydrated_attachments, upload_ids)[0]

        async def generate_events():
            stream_started.set()
            current_task = asyncio.current_task()
            if current_task is not None:
                active_turn_tasks[session_id] = current_task
            stopped_before_stream = session_id in pending_turn_stops
            pending_turn_stops.discard(session_id)
            assistant_parts: list[str] = []
            pending_proposal: AgentProposal | None = None
            pending_download: bytes | None = None
            completed = False
            outcome = "cancelled"
            error_code = None
            usage = None
            turn_messages = [ChatMessage(role="user", content=history_question)]
            assistant_segment: list[str] = []
            try:
                if dropped_history:
                    yield _sse_event("history_trimmed", {"dropped": dropped_history})
                if stopped_before_stream:
                    raise asyncio.CancelledError
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
                        ),
                        attachments=hydrated_attachments,
                        optimizer_result=latest_artifact.content if latest_artifact is not None else None,
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
                        elif isinstance(event, AgentDownload):
                            pending_download = event.content
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
                if completion.history_trimmed_count and completion.history_trimmed_count != dropped_history:
                    yield _sse_event("history_trimmed", {"dropped": completion.history_trimmed_count})
                if completion.proposal_saved:
                    yield _sse_event("proposal", {"diff": pending_proposal.diff})
                if pending_download is not None:
                    if store.save_download(session_id, turn_id, pending_download):
                        yield _sse_event("download", {"download_id": turn_id})
                    else:
                        yield _sse_event(
                            "error",
                            {
                                "message": "The generated ZIP could not be retained because the service memory limit was reached."
                            },
                        )
                done = {"message_id": turn_id}
                if history_saved is not None:
                    done["history_saved"] = history_saved
                yield _sse_event("done", done)
            except asyncio.CancelledError:
                raise
            except ProviderError as exc:
                outcome, error_code = "failed", "provider_error"
                yield _sse_event("error", {"message": exc.user_message or PROVIDER_ERROR})
            except SandboxDownloadError as exc:
                outcome, error_code = "failed", "download_error"
                yield _sse_event("error", {"message": str(exc)})
            except SandboxCommandTimeoutError:
                outcome, error_code = "failed", "sandbox_command_timeout"
                yield _sse_event("error", {"message": SANDBOX_COMMAND_TIMEOUT_ERROR})
            except SandboxTurnTimeoutError:
                outcome, error_code = "failed", "sandbox_timeout"
                yield _sse_event("error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})
            except SandboxCandidateError as exc:
                outcome, error_code = "failed", "candidate_validation"
                logger.warning("AI candidate validation failed: %s", exc)
                yield _sse_event(
                    "error",
                    {"message": CANDIDATE_VALIDATION_ERROR + (f"\n\n{exc.user_message}" if exc.user_message else "")},
                )
            except SandboxError:
                outcome, error_code = "failed", "sandbox_error"
                logger.exception("AI sandbox turn failed")
                yield _sse_event("error", {"message": "The temporary AI sandbox failed. Please try again."})
            except Exception:
                outcome, error_code = "failed", "internal_error"
                logger.exception("Unexpected AI stream failure")
                yield _sse_event("error", {"message": "The AI response failed unexpectedly."})
            finally:
                pending_turn_stops.discard(session_id)
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
                pending_turn_stops.discard(session_id)
                if history_log is not None:
                    await history_log.write("finish_turn", turn_id, "", "cancelled", None, None)
                release_turn()

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
