"""Browser-owned session state, lifetime, and retained-byte budgets."""

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

# This file is mostly AI generated.

import math
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from uuid import uuid4

from fastapi import HTTPException

from .agent_session import AgentSession, ProposalValidationError, schedule_revision
from .config import AiSettings
from .context import (
    PROPOSAL_DECISION_HISTORY,
    PROPOSAL_REJECTED_HISTORY,
    cap_transcript,
    drop_oldest_exchange,
    entries_from_legacy_history,
    project_history,
    projected_history,
    removal_event,
    retained_entries,
    upload_event,
)
from .lifecycle import TurnSnapshot
from .transcript import (
    AgentMessage,
    AppEventEntry,
    AssistantMessage,
    ProposalDecisionEntry,
    UserMessage,
    entry_from_record,
    entry_record,
    entry_text,
)
from .workspace import SandboxAttachment

SESSION_MEMORY_LIMIT_MESSAGE = "The AI service has reached its memory limit."


def _text_bytes(value: object) -> int:
    """Return the UTF-8 size of one chat content value, ignoring inline image data."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, list):
        return sum(len(part.get("text", "").encode("utf-8")) for part in value if part.get("type") == "text")
    return 0


def _transcript_bytes(entries: Sequence[AgentMessage]) -> int:
    # Count retained partial output even when model context replaces it with a note.
    return sum(
        _text_bytes(
            PROPOSAL_DECISION_HISTORY[entry.decision] if isinstance(entry, ProposalDecisionEntry) else entry_text(entry)
        )
        for entry in entries
    )


def _session_bytes(session: "AgentSession") -> int:
    """Return the text and file bytes one session retains."""
    total = _text_bytes(session.schedule_yaml) + _text_bytes(session.proposal_yaml) + _text_bytes(session.proposal_diff)
    total += _transcript_bytes(session.transcript)
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
        self._sessions: dict[str, AgentSession] = {}
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

    def _recount(self, session: AgentSession) -> None:
        """Refresh one session's contribution to the retained total, under the caller's lock."""
        previous = self._session_bytes.get(session.id, 0)
        current = _session_bytes(session)
        self._session_bytes[session.id] = current
        self._retained_bytes += current - previous

    def _charge(self, session: AgentSession, delta: int) -> None:
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

    def _trim_history_to_budget(self, session: AgentSession, protected_messages: int) -> None:
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
            removed = drop_oldest_exchange(session.transcript, protected_messages)
            if not removed:
                break
            self._charge(session, -_transcript_bytes(removed))
            session.dropped_history_messages += len(projected_history(removed))

    def _effective_trimmed_count(self, session: AgentSession) -> int:
        """Count retained-history and prompt-budget omissions visible to a client."""
        return (
            session.dropped_history_messages
            + project_history(session.transcript, self._settings.max_history_chars).dropped_messages
        )

    def _cap_history(self, session: AgentSession, keep_entries: int = 0) -> None:
        session.dropped_history_messages += cap_transcript(
            session.transcript, self._settings.max_history_messages, self._settings.max_history_chars, keep_entries
        )

    def create(self, owner_token: str, schedule_yaml: str) -> AgentSession:
        """Create a session after pruning expired entries."""
        with self._lock:
            self._prune_expired()
            self._make_room()
            if len(self._sessions) >= self._settings.max_sessions:
                raise HTTPException(status_code=429, detail="The AI service has reached its session limit.")
            self._require_capacity(_text_bytes(schedule_yaml))
            session = AgentSession(
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
            return self._reserve(session, accepting_steering=True)

    def begin_background(self, session_id: str) -> TurnSnapshot | None:
        """Reserve an idle session for a trusted background-triggered turn."""
        with self._lock:
            self._prune_expired()
            session = self._sessions.get(session_id)
            if session is None or session.active:
                return None
            return self._reserve(session, accepting_steering=False)

    def _reserve(self, session: AgentSession, *, accepting_steering: bool) -> TurnSnapshot:
        snapshot = session.begin_run(accepting_steering=accepting_steering)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        return snapshot

    def get_owned(self, session_id: str, owner_token: str | None) -> AgentSession:
        with self._lock:
            return self._get_owned(session_id, owner_token)

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
                    "transcript": [
                        {"type": kind, "payload": payload} for kind, payload in map(entry_record, session.transcript)
                    ],
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
            state = dict(record["state"])
            if "transcript" in state:
                state["transcript"] = [
                    entry_from_record(entry["type"], entry["payload"]) for entry in state["transcript"]
                ]
            else:
                state["transcript"] = entries_from_legacy_history(state.pop("history"))
            session = AgentSession(
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
        turn_messages: Sequence[AgentMessage] = (),
    ) -> TurnCompletion:
        """Save a completed turn only while its conversation version is current."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return TurnCompletion(turn_saved=False, proposal_saved=False)
            completed_turn = (
                retained_entries(turn_messages)
                if turn_messages
                else [UserMessage(user_message), AssistantMessage(assistant_message)]
            )
            if not session.commit_turn(snapshot, completed_turn, proposal):
                self._recount(session)
                return TurnCompletion(turn_saved=False, proposal_saved=False)
            self._cap_history(session, len(completed_turn))
            proposal_saved = proposal is not None
            self._recount(session)
            self._trim_history_to_budget(session, min(len(completed_turn), len(session.transcript)))
            return TurnCompletion(
                turn_saved=True,
                proposal_saved=proposal_saved,
                history_trimmed_count=self._effective_trimmed_count(session),
                context_used_chars=project_history(session.transcript, self._settings.max_history_chars).used_chars,
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
            if not session.check_steering(message_id, self._settings.max_history_messages):
                return
            message_bytes = _text_bytes(message)
            self._require_capacity(message_bytes)
            session.queue_steering(message_id, message)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            self._charge(session, message_bytes)

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]:
        """Drain queued messages and close the final race when a response is done."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.active:
                return []
            queued = session.take_steering(close_if_empty)
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
            session.update_schedule(schedule_yaml)
            self._cap_history(session)
            self._recount(session)

    def approve_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> str:
        """Apply the session's approval policy and reconcile retained-byte accounting."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            try:
                approved = session.approve_proposal(base_sha256, self._settings.max_schedule_bytes)
            except ProposalValidationError:
                session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
                raise
            finally:
                self._cap_history(session)
                self._recount(session)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            return approved

    def discard_proposal(
        self,
        session_id: str,
        owner_token: str | None,
        history_event: str = PROPOSAL_REJECTED_HISTORY,
    ) -> None:
        """Drop a pending proposal and record why it was dropped once."""
        with self._lock:
            session = self._get_owned(session_id, owner_token)
            session.discard_proposal(history_event)
            self._cap_history(session)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            self._recount(session)

    def abort(self, session_id: str, snapshot: TurnSnapshot) -> None:
        """Only the owner of a reservation may release it."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.turn is snapshot:
                session.abort(snapshot)
                self._recount(session)

    def _append_history_event(self, session: AgentSession, content: str) -> None:
        """Append one trusted application event within the caller's lock."""
        session.transcript.append(AppEventEntry(content))
        self._cap_history(session)

    def _get_owned(self, session_id: str, owner_token: str | None) -> AgentSession:
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
