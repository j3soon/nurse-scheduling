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
from collections import Counter
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing, asynccontextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from ruamel.yaml.error import YAMLError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..loader import _load_yaml
from ..sentry import SentryClientAddressMiddleware, init_sentry
from ..server.auth import AUTH_SCHEME, create_auth_dependency, create_auth_registry
from ..service_logging import configure_service_logging
from ..version import get_app_version
from .agent_types import AgentProposal, AgentReasoning, AgentSteering, AgentText, AgentToolStart, AgentToolUse
from .background import (
    CANDIDATE_VALIDATION_ERROR,
    PROPOSAL_APPROVED_HISTORY,
    PROPOSAL_INVALID_HISTORY,
    PROPOSAL_REJECTED_HISTORY,
    PROVIDER_ERROR,
    SANDBOX_COMMAND_TIMEOUT_ERROR,
    SANDBOX_TURN_TIMEOUT_ERROR,
    SCHEDULE_CHANGED_DISCARDED_EVENT,
    SCHEDULE_CHANGED_EVENT,
    STALE_TURN_ERROR,
    SessionEventBroker,
    build_provider_messages,
    context_usage,
    history_chars,
    history_context_chars,
    model_input,
    recent_history,
    removal_event,
    run_background_turn,
    upload_event,
)
from .config import AiSettings, validate_ai_auth_credentials
from .history import ChatHistory, stop_maintenance
from .lifecycle import SessionTurns, Turn, TurnSnapshot
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
from .turns import TurnJournal, append_compacted
from .validation import new_schedule_issues, validate_frontend_schedule_yaml
from .workspace import (
    SANDBOX_SYSTEM_PROMPT,
    AgentDownload,
    AgentScheduleChange,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxCommandTimeoutError,
    SandboxDownloadError,
    SandboxTurnTimeoutError,
    WorkspaceLimits,
)
from .workspace_tools import run_workspace

SERVICE_NAME = "nurse-scheduling-ai-api"
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


def _schedule_data(schedule_yaml: str) -> object:
    """Parse a schedule for comparison, so a formatting-only change is not reported as an edit."""
    try:
        return _load_yaml(schedule_yaml.encode(), reject_aliases=True)
    except (ValueError, YAMLError):
        return schedule_yaml


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so a stale proposal cannot be applied."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


def owner_cookie_token(owner: str | None) -> str:
    """Return a normalized browser owner token or replace an invalid value."""
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
    version: int = 0
    turn: TurnSnapshot | None = None

    @property
    def active(self) -> bool:
        return self.turn is not None

    proposal_yaml: str = ""
    proposal_diff: str = ""
    downloads: dict[str, bytes] = field(default_factory=dict)
    uploads: dict[str, SandboxAttachment] = field(default_factory=dict)
    last_used: float = field(default_factory=time.monotonic)
    """Last owner access, which orders eviction. A restored session keeps its stored expiry."""


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
        + sum(_text_bytes(text) for _message_id, text in (session.turn.steering_queue if session.turn else ()))
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
    context_used_chars: int = 0


class SessionStore:
    """Bounded in-memory session storage for the first experimental slice."""

    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, ChatSession] = {}
        self._retained_bytes = 0
        self._session_bytes: dict[str, int] = {}
        self._lock = threading.RLock()
        self._on_retire: Callable[[str], None] | None = None
        self._evictable: Callable[[str], bool] | None = None

    def on_retire(self, callback: Callable[[str], None]) -> None:
        """Register the cleanup that follows every dropped session."""
        self._on_retire = callback

    def allow_eviction(self, evictable: Callable[[str], bool]) -> None:
        """Let a full store unload idle sessions that recovery storage can restore."""
        self._evictable = evictable

    def _make_room(self) -> None:
        """Unload the least recently used idle session at the session limit, under the caller's lock.

        Sessions live for the whole recovery period, so without eviction a month of chats
        would hold every slot. Only uploads, downloads, and finished optimizer results are
        lost, as after a restart.
        """
        if self._evictable is None or len(self._sessions) < self._settings.max_sessions:
            return
        idle = [session for session in self._sessions.values() if not session.active and self._evictable(session.id)]
        if idle:
            self._retire(min(idle, key=lambda session: session.last_used).id)

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
        """Limit retained messages without leaving an assistant reply at the front.

        Past the prompt history budget, drop the oldest messages until half the budget remains.
        Cutting in large steps keeps the prompt prefix unchanged for many turns, so the provider
        can reuse its cache. Cutting one message per turn would change the prefix every time.
        """
        overflow = max(0, len(session.history) - max(2, self._settings.max_history_messages))
        if history_chars(session.history) > self._settings.max_history_chars:
            # Never cut into the newest completed exchange. Per-request trimming covers what still overflows.
            last_reply = max(
                (index for index, message in enumerate(session.history) if message["role"] == "assistant"), default=0
            )
            newest_exchange = max(
                (index for index in range(last_reply) if session.history[index]["role"] == "user"), default=0
            )
            remaining = history_chars(session.history[overflow:])
            while overflow < newest_exchange and remaining > self._settings.max_history_chars // 2:
                remaining -= history_chars(session.history[overflow : overflow + 1])
                overflow += 1
            while overflow < newest_exchange and session.history[overflow]["role"] != "user":
                overflow += 1
        if overflow:
            while overflow < len(session.history) and session.history[overflow]["role"] != "user":
                overflow += 1
            del session.history[:overflow]
            session.dropped_history_messages += overflow

    def create(self, owner_token: str, schedule_yaml: str) -> ChatSession:
        """Create a session after pruning expired entries."""
        with self._lock:
            self._prune_expired()
            self._make_room()
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

    def begin(self, session_id: str, owner_token: str | None) -> TurnSnapshot:
        """Reserve the current conversation version for one foreground turn."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            if session.active:
                raise HTTPException(status_code=409, detail="This chat session already has an active response.")
            return self._reserve(session, accepting_steering=True)

    def begin_background(self, session_id: str) -> TurnSnapshot | None:
        """Reserve an idle session for a trusted background-triggered turn."""
        with self._lock:
            self._prune_expired()
            session = self._sessions.get(session_id)
            if session is None or session.active:
                return None
            return self._reserve(session, accepting_steering=False)

    def _reserve(self, session: ChatSession, *, accepting_steering: bool) -> TurnSnapshot:
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        snapshot = TurnSnapshot(
            history=list(session.history),
            schedule_yaml=session.schedule_yaml,
            version=session.version,
            proposal_yaml=session.proposal_yaml,
            proposal_diff=session.proposal_diff,
            accepting_steering=accepting_steering,
            dropped_history_messages=session.dropped_history_messages,
        )
        session.turn = snapshot
        return snapshot

    def require_owned(self, session_id: str, owner_token: str | None) -> None:
        """Validate access to a session without exposing its state."""
        with self._lock:
            self._get_owned(session_id, owner_token)

    def recovery_state(self, session_id: str) -> tuple[str, float, dict]:
        with self._lock:
            session = self._sessions[session_id]
            return (
                session.owner_token,
                time.time() + max(0, session.expires_at - time.monotonic()),
                {
                    "schedule_yaml": session.schedule_yaml,
                    "history": [dict(message) for message in session.history],
                    "proposal_yaml": session.proposal_yaml,
                    "proposal_diff": session.proposal_diff,
                    "dropped_history_messages": session.dropped_history_messages,
                },
            )

    def restore(self, session_id: str, owner: str, record: dict) -> None:
        with self._lock:
            self._prune_expired()
            remaining = record["expires_at"] - time.time()
            if remaining <= 0:
                raise HTTPException(status_code=404, detail="Chat session not found.")
            self._make_room()
            if len(self._sessions) >= self._settings.max_sessions:
                raise HTTPException(status_code=429, detail="The AI service has reached its session limit.")
            state = record["state"]
            session = ChatSession(
                id=session_id,
                owner_token=owner,
                expires_at=time.monotonic() + remaining,
                revision=schedule_revision(state["schedule_yaml"]),
                **state,
            )
            self._require_capacity(_session_bytes(session))
            self._sessions[session_id] = session
            self._recount(session)

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
            filenames = {item.filename for item in session.uploads.values()}
            retained_uploads = []
            for upload in uploads:
                filename = _unique_filename(upload.filename, filenames)
                filenames.add(filename)
                retained_uploads.append(replace(upload, filename=filename, id=str(uuid4())))
            first_index = len(session.uploads) + 1
            history_event = upload_event(retained_uploads, first_index)
            self._require_capacity(sum(len(upload.data) for upload in retained_uploads) + _text_bytes(history_event))
            session.uploads.update((item.id, item) for item in retained_uploads)
            self._append_history_event(session, history_event)
            self._recount(session)
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
            if upload_id not in session.uploads:
                raise HTTPException(status_code=404, detail="The uploaded file is no longer available.")
            index = list(session.uploads).index(upload_id) + 1
            upload = session.uploads.pop(upload_id)
            self._append_history_event(session, removal_event(upload, index))
            self._recount(session)
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

    def remove_download(self, session_id: str, owner_token: str | None, download_id: str) -> None:
        """Remove an owned generated ZIP and reclaim its bytes."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            try:
                content = session.downloads.pop(download_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="This generated ZIP is no longer available.") from None
            self._charge(session, -len(content))
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

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
        snapshot: TurnSnapshot,
        turn_messages: Sequence[ChatMessage] = (),
    ) -> TurnCompletion:
        """Save a completed turn only while its conversation version is current."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.turn is not snapshot:
                return TurnCompletion(turn_saved=False, proposal_saved=False)
            session.turn = None
            if session.version != snapshot.version:
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
            self._recount(session)
            self._trim_history_to_budget(session, min(len(completed_turn), len(session.history)))
            return TurnCompletion(
                turn_saved=True,
                proposal_saved=proposal_saved,
                history_trimmed_count=self._effective_trimmed_count(session),
                context_used_chars=history_context_chars(session.history, self._settings.max_history_chars),
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
            turn = session.turn
            if turn is None or not turn.accepting_steering:
                raise HTTPException(status_code=409, detail="The active response is no longer accepting messages.")
            if message_id in turn.steering_ids:
                return
            # Counted over the whole turn, not the drained queue, because the seen-ID set
            # that makes a retried POST idempotent is never emptied mid-turn.
            if len(turn.steering_ids) >= self._settings.max_history_messages:
                raise HTTPException(status_code=429, detail="Too many messages are already queued.")
            message_bytes = _text_bytes(message)
            self._require_capacity(message_bytes)
            turn.steering_queue.append((message_id, message))
            turn.steering_ids.add(message_id)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            self._charge(session, message_bytes)

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]:
        """Drain queued messages and close the final race when a response is done."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.active:
                return []
            turn = session.turn
            queued = list(turn.steering_queue)
            turn.steering_queue.clear()
            if close_if_empty and not queued:
                turn.accepting_steering = False
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
            data_changed = _schedule_data(session.schedule_yaml) != _schedule_data(schedule_yaml)
            had_proposal = bool(session.proposal_yaml)
            if session.schedule_yaml != schedule_yaml or had_proposal:
                session.version += 1
            session.schedule_yaml = schedule_yaml
            session.revision = schedule_revision(schedule_yaml)
            session.proposal_yaml = ""
            session.proposal_diff = ""
            if data_changed or had_proposal:
                self._append_history_event(
                    session, SCHEDULE_CHANGED_DISCARDED_EVENT if had_proposal else SCHEDULE_CHANGED_EVENT
                )
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
            session.version += 1
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
            session.version += 1
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
                session.version += 1
                self._append_history_event(session, history_event)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            self._recount(session)

    def abort(self, session_id: str, snapshot: TurnSnapshot) -> None:
        """Only the owner of a reservation may release it."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.turn is snapshot:
                session.turn = None
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
        session.last_used = time.monotonic()
        return session

    def discard(self, session_id: str) -> None:
        """Drop a session that was never handed to a client."""
        with self._lock:
            if session_id in self._sessions:
                self._retire(session_id)

    def _retire(self, session_id: str) -> None:
        """Drop one session and everything keyed by it, under the caller's lock."""
        del self._sessions[session_id]
        self._forget(session_id)
        if self._on_retire is not None:
            self._on_retire(session_id)

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired_ids = [session_id for session_id, session in self._sessions.items() if session.expires_at <= now]
        for session_id in expired_ids:
            self._retire(session_id)


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
    shutting_down = False
    recovery_lock = asyncio.Lock()
    state_write_locks: dict[str, asyncio.Lock] = {}
    session_pins: Counter[str] = Counter()
    unsaved_sessions: set[str] = set()
    concurrency_limit = asyncio.Semaphore(settings.max_concurrent_requests)
    auth_registry = create_auth_registry(settings.auth_token, settings.auth_tokens)
    require_auth = create_auth_dependency(auth_registry)

    def state_write_lock(session_id: str) -> asyncio.Lock:
        """Serialize each state capture with its write, so an older state never commits last."""
        return state_write_locks.setdefault(session_id, asyncio.Lock())

    def pin_session(session_id: str) -> Callable[..., None]:
        """Keep a session loaded until the returned release runs.

        The store marks a session idle before its worker saves the outcome, and an
        endpoint changes a session before its write starts. Eviction must wait for both.
        """
        session_pins[session_id] += 1

        def release(*_args: object) -> None:
            session_pins[session_id] -= 1
            if session_pins[session_id] <= 0:
                del session_pins[session_id]

        return release

    def record_save(session_id: str, saved: bool) -> bool:
        """Keep a session whose newest state failed to save, so eviction never drops its only copy."""
        if saved:
            unsaved_sessions.discard(session_id)
        elif session_id in store._sessions:
            unsaved_sessions.add(session_id)
        return saved

    async def save_session(session_id: str, credential_id: str | None = None) -> bool:
        if history_log is None:
            return True
        release = pin_session(session_id)
        try:
            async with state_write_lock(session_id):
                if session_id not in store._sessions:
                    return True
                recovery_state = store.recovery_state(session_id)
                saved = await turn_journal.save_outcomes(session_id, recovery_state) and await history_log.write(
                    "save_recovery_session", session_id, *recovery_state, credential_id
                )
                return record_save(session_id, saved)
        finally:
            release()

    async def restore_session(request: Request, owner: str | None = Cookie(default=None, alias=OWNER_COOKIE)) -> None:
        session_id = request.path_params.get("session_id")
        if session_id is None:
            return
        try:
            store.require_owned(session_id, owner)
            return
        except HTTPException as exc:
            if exc.status_code != 404 or history_log is None or owner is None:
                raise
        async with recovery_lock:
            if session_id in store._sessions:
                store.require_owned(session_id, owner)
                return
            try:
                try:
                    UUID(session_id)
                    UUID(owner)
                except ValueError:
                    raise HTTPException(status_code=404, detail="Chat session not found.") from None
                record = await history_log.read("load_recovery_session", session_id, owner)
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
            if record is None:
                raise HTTPException(status_code=404, detail="Chat session not found.")
            store.restore(session_id, owner, record)
            release = pin_session(session_id)
            try:
                for turn in turn_journal.restore(session_id, record["turns"]):
                    if not turn.terminal:
                        async with state_write_lock(session_id):
                            saved = await turn_journal.finish(
                                turn,
                                "error",
                                {
                                    "message": "The AI service restarted during this response. Your question and saved output were recovered. You can retry this turn."
                                },
                                state=store.recovery_state(session_id),
                                metadata={"error_code": "service_restart"},
                            )
                            record_save(session_id, saved)
                event_broker.restore(session_id, record["background_events"])
                if record["background_status"] == "running":
                    await event_broker.emit(
                        session_id,
                        "error",
                        {
                            "message": "The AI service restarted during this background response. Its saved output was recovered."
                        },
                        metadata={"error_code": "service_restart"},
                    )
            finally:
                release()

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
        turn = turns.start(
            session_id,
            lambda turn: run_background_turn(
                session_id,
                prompt,
                artifact,
                turn=turn,
                settings=settings,
                store=store,
                event_broker=event_broker,
                concurrency_limit=concurrency_limit,
                history_log=history_log,
                provider=provider,
                sandbox_factory=sandbox_factory,
                session_optimizer=session_optimizer,
            ),
            background=True,
        )
        turn.task.add_done_callback(pin_session(session_id))
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

    async def persist_background_event(
        session_id: str, event_id: int, event_type: str, data: dict, metadata: dict | None = None
    ) -> None:
        if history_log is None:
            return
        # Deliver terminal and optimizer status events even when saving fails. Otherwise an
        # outage leaves the browser waiting and stops the optimizer from waking the agent.
        if event_type in {"done", "stopped", "stale", "error"}:
            if event_type == "stopped" and shutting_down:
                return
            async with state_write_lock(session_id):
                if session_id not in store._sessions:
                    return
                saved = await history_log.write(
                    "finish_recovery_turn",
                    session_id,
                    *store.recovery_state(session_id),
                    "background",
                    event_id,
                    event_type,
                    data,
                    metadata,
                )
                record_save(session_id, saved)
            return
        if event_type == "optimization":
            if await save_session(session_id):
                await history_log.write("append_recovery_event", session_id, "background", event_id, event_type, data)
            return
        if event_type == "turn_start" and not await save_session(session_id):
            raise RuntimeError("AI message recovery is temporarily unavailable.")
        if not await history_log.write("append_recovery_event", session_id, "background", event_id, event_type, data):
            raise RuntimeError("AI message recovery is temporarily unavailable.")

    event_broker.on_publish = persist_background_event
    if history_log is not None:
        event_broker.load_snapshot = lambda session_id: history_log.read("load_background_snapshot", session_id)

    def retire_session(session_id: str) -> None:
        """Release everything keyed by a session once the store drops it."""
        turns.retire(session_id)
        state_write_locks.pop(session_id, None)
        unsaved_sessions.discard(session_id)
        session_optimizer.forget_session(session_id)
        event_broker.forget_session(session_id)
        turn_journal.forget_session(session_id)

    store.on_retire(retire_session)
    if history_log is not None:
        store.allow_eviction(
            lambda session_id: (
                session_id not in session_pins
                and session_id not in unsaved_sessions
                and not turn_journal.has_unsaved_outcome(session_id)
                and not turns.busy(session_id)
                and not session_optimizer.has_unfinished_run(session_id)
            )
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        nonlocal shutting_down
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
                    shutting_down = True
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
            saved = await save_session(session.id, http_request.state.auth_credential_id)
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
        store.require_owned(session_id, owner)
        try:
            existing = None if body.message_id is None else await turn_journal.get(session_id, body.message_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        if existing is not None:
            if existing.question != question:
                raise HTTPException(status_code=409, detail="This message ID belongs to a different question.")
            return turn_response(existing, body.last_event_id, owner, snapshot=True)
        replay_turn = None

        async def run_foreground(turn: Turn) -> None:
            nonlocal replay_turn
            snapshot = store.begin(session_id, owner)
            turn.admitting = True
            try:
                hydrated_attachments = store.attachments(session_id)
                turn_id = turn.id
                request_id = body.message_id or turn_id
                request_logger.info(
                    "AI request started session_id=%s question_chars=%s question=%s files=%s",
                    session_id,
                    len(question),
                    json.dumps(_question_log_preview(question), ensure_ascii=False),
                    len(hydrated_attachments),
                )
                if not await save_session(session_id):
                    raise RuntimeError("AI message recovery is temporarily unavailable.")
                replay_turn = await turn_journal.start(
                    session_id,
                    turn_id,
                    request_id,
                    question,
                    {
                        "model": settings.provider_model,
                        "auth_credential_id": request.state.auth_credential_id,
                        "attachment_count": len(hydrated_attachments),
                    },
                )
                turn.admitting = False
                turn.ready.set_result(True)
                history, schedule_yaml = snapshot.history, snapshot.schedule_yaml
                proposal_yaml, proposal_diff = snapshot.proposal_yaml, snapshot.proposal_diff
                previously_dropped = snapshot.dropped_history_messages
                history_question = question
                saved_outcome = None
                recovery_metadata = {}

                async def generate_events():
                    nonlocal saved_outcome
                    assistant_parts: list[str] = []
                    pending_proposal: AgentProposal | None = None
                    pending_download: bytes | None = None
                    completed = False

                    error_code = None
                    usage = None
                    last_call: TokenUsage | None = None
                    turn_messages = [ChatMessage(role="user", content=history_question)]
                    assistant_segment: list[str] = []
                    try:
                        if turn.cancelled or await turn_journal.was_stopped(session_id, request_id):
                            raise asyncio.CancelledError
                        latest_artifact = await session_optimizer.latest_result_artifact(session_id)
                        retained_history = recent_history(history, settings.max_history_chars)
                        dropped_history = previously_dropped + len(history) - len(retained_history)
                        messages = build_provider_messages(
                            retained_history,
                            schedule_yaml,
                            question,
                            hydrated_attachments,
                            system_prompt=SANDBOX_SYSTEM_PROMPT,
                            pending_proposal=bool(proposal_yaml),
                            optimizer_result_available=latest_artifact is not None,
                            max_history_chars=settings.max_history_chars,
                            max_download_bytes=settings.max_download_bytes,
                        )
                        yield _sse_event(
                            "model_input", model_input(messages, len(retained_history), dropped_history, "question")
                        )
                        context_chars = history_context_chars(history, settings.max_history_chars)
                        yield _sse_event("context_usage", context_usage(context_chars, settings))
                        if dropped_history:
                            yield _sse_event("history_trimmed", {"dropped": dropped_history})
                        async with concurrency_limit:
                            agent_events = run_workspace(
                                provider,
                                sandbox_factory,
                                schedule_yaml,
                                messages,
                                WorkspaceLimits.from_settings(settings),
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
                                optimizer_context=latest_artifact.schedule_context
                                if latest_artifact is not None
                                else None,
                            )
                            async with aclosing(agent_events):
                                async for event in agent_events:
                                    if isinstance(event, AgentText):
                                        assistant_parts.append(event.text)
                                        assistant_segment.append(event.text)
                                        yield _sse_event("delta", {"text": event.text})
                                    elif isinstance(event, AgentReasoning):
                                        yield _sse_event("reasoning", {"text": event.text})
                                    elif isinstance(event, TokenUsage):
                                        usage = event if usage is None else usage + event
                                        last_call = event
                                        yield _sse_event(
                                            "context_usage", context_usage(context_chars, settings, last_call, provider)
                                        )
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
                                            turn_messages.append(
                                                ChatMessage(role="assistant", content="".join(assistant_segment))
                                            )
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
                            snapshot=snapshot,
                            turn_messages=turn_messages,
                        )
                        completed = True
                        turn.finishing = True
                        saved_outcome = (
                            ("done", {"message_id": turn_id})
                            if completion.turn_saved
                            else ("stale", {"message": STALE_TURN_ERROR})
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
                                    "warning",
                                    {
                                        "message": "The generated ZIP could not be retained because the service memory limit was reached."
                                    },
                                )
                        done = {"message_id": turn_id}
                        yield _sse_event(
                            "context_usage", context_usage(completion.context_used_chars, settings, last_call, provider)
                        )
                        yield _sse_event("done", done)
                    except asyncio.CancelledError:
                        if completed:
                            # Stop can arrive while a completed answer is being persisted.
                            yield (
                                _sse_event("done", {"message_id": turn_id})
                                if completion.turn_saved
                                else _sse_event("stale", {"message": STALE_TURN_ERROR})
                            )
                        else:
                            yield _sse_event("stopped", {"message_id": turn_id})
                    except ProviderError as exc:
                        error_code = "provider_error"
                        yield _sse_event("error", {"message": exc.user_message or PROVIDER_ERROR})
                    except SandboxDownloadError as exc:
                        error_code = "download_error"
                        yield _sse_event("error", {"message": str(exc)})
                    except SandboxCommandTimeoutError:
                        error_code = "sandbox_command_timeout"
                        yield _sse_event("error", {"message": SANDBOX_COMMAND_TIMEOUT_ERROR})
                    except SandboxTurnTimeoutError:
                        error_code = "sandbox_timeout"
                        yield _sse_event("error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})
                    except SandboxCandidateError as exc:
                        error_code = "candidate_validation"
                        logger.warning("AI candidate validation failed: %s", exc)
                        yield _sse_event(
                            "error",
                            {
                                "message": CANDIDATE_VALIDATION_ERROR
                                + (f"\n\n{exc.user_message}" if exc.user_message else "")
                            },
                        )
                    except SandboxError:
                        error_code = "sandbox_error"
                        logger.exception("AI sandbox turn failed")
                        yield _sse_event("error", {"message": "The temporary AI sandbox failed. Please try again."})
                    except Exception:
                        error_code = "internal_error"
                        logger.exception("Unexpected AI stream failure")
                        yield _sse_event("error", {"message": "The AI response failed unexpectedly."})
                    finally:
                        if not completed:
                            store.abort(session_id, snapshot)
                        recovery_metadata.update(error_code=error_code, usage=asdict(usage) if usage else None)

                queue = asyncio.Queue(maxsize=64)
                terminal = None

                async def collect_events() -> None:
                    source = generate_events()
                    try:
                        async for block in source:
                            lines = block.splitlines()
                            event_type = next(line[7:] for line in lines if line.startswith("event: "))
                            data = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
                            await queue.put((event_type, data))
                    except asyncio.CancelledError:
                        await queue.put(saved_outcome or ("stopped", {"message_id": turn_id}))
                    finally:
                        await source.aclose()
                        await queue.put(None)

                collector = asyncio.create_task(collect_events(), name=f"ai-output-{turn_id}")
                try:
                    ended = False
                    while not ended:
                        batch = []
                        event = await queue.get()
                        while True:
                            if event is None:
                                ended = True
                                break
                            if event[0] in {"delta", "reasoning"}:
                                append_compacted(batch, *event)
                            else:
                                batch.append({"type": event[0], "data": event[1]})
                            if queue.empty():
                                break
                            event = queue.get_nowait()
                        for event in batch:
                            if event["type"] in {"done", "stopped", "stale", "error"}:
                                terminal = (event["type"], event["data"])
                            else:
                                await turn_journal.publish(replay_turn, event["type"], event["data"])
                except asyncio.CancelledError:
                    terminal = saved_outcome or terminal
                    if terminal is None and not shutting_down:
                        terminal = ("stopped", {"message_id": turn_id})
                except Exception:
                    logger.exception("AI turn recovery failed session_id=%s", session_id)
                    terminal = (
                        "error",
                        {
                            "message": "AI message recovery is temporarily unavailable. Reconnect to check the saved response."
                        },
                    )
                finally:
                    turn.finishing = True
                    if not collector.done():
                        collector.cancel()
                    # Release a producer waiting for a full queue before joining it. Keep a
                    # terminal event that the turn queued before shutdown.
                    while not queue.empty():
                        event = queue.get_nowait()
                        if terminal is None and event and event[0] in {"done", "stopped", "stale", "error"}:
                            terminal = event
                    await asyncio.gather(collector, return_exceptions=True)
                    if session_id in store._sessions:
                        if shutting_down and terminal is not None and terminal[0] == "stopped":
                            terminal = None
                        if terminal is not None:
                            async with state_write_lock(session_id):
                                saved = await turn_journal.finish(
                                    replay_turn,
                                    *terminal,
                                    state=store.recovery_state(session_id),
                                    metadata=recovery_metadata,
                                )
                                record_save(session_id, saved)
                        else:
                            await save_session(session_id)
            finally:
                turn.admitting = False
                store.abort(session_id, snapshot)

        turn = turns.start(session_id, run_foreground, message_id=body.message_id)
        turn.task.add_done_callback(pin_session(session_id))
        try:
            if not await asyncio.shield(turn.ready):
                if turn.task.cancelled():
                    raise HTTPException(status_code=409, detail="The response was stopped before it started.")
                await turn.wait()
        except asyncio.CancelledError:
            if not turn.ready.done() or not turn.ready.result():
                turn.cancel()
                await asyncio.shield(turn.done)
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        return turn_response(replay_turn, body.last_event_id, owner)

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
        if not await save_session(session_id):
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
                await save_session(session_id)
                raise HTTPException(status_code=409, detail="The proposed schedule is no longer valid.")
        schedule_yaml = store.adopt_proposal(session_id, owner, request.base_sha256)
        # The proposal is gone once adopted, so a failed save is reported rather than refused.
        history_saved = await save_session(session_id)
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
        history_saved = await save_session(session_id)
        refresh_owner_cookie(response, owner)
        return ProposalRejectionResponse(history_saved=history_saved)

    return app
