"""Session state, message steering, and schedule proposal ownership."""

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
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .agent_session import AgentSession, RunCompletion, schedule_revision
from .candidate import PendingProposal
from .config import AiSettings
from .context import PROPOSAL_DECISION_HISTORY, history_chars, project_history, projected_history, upload_event
from .history import EntryRow
from .lifecycle import RunSnapshot
from .session_event_stream import SessionEventStream
from .transcript import AgentMessage, ProposalDecision, ProposalDecisionEntry, entry_text, starts_exchange
from .workspace import SandboxAttachment

__all__ = ["SessionStore", "schedule_revision"]

SESSION_RETENTION_LIMIT_MESSAGE = "The AI service has reached its session text and file retention limit."


def _text_bytes(value: str) -> int:
    """Return the UTF-8 byte count of retained text, excluding inline image data."""
    return len(value.encode("utf-8"))


def _proposal_bytes(proposal: PendingProposal | None) -> int:
    return 0 if proposal is None else _text_bytes(proposal.schedule_yaml) + _text_bytes(proposal.diff)


def _session_bytes(session: "AgentSession") -> int:
    """Return the text and file bytes one session retains."""
    total = _text_bytes(session.schedule_yaml) + _proposal_bytes(session.pending_proposal)
    total += sum(
        _text_bytes(
            PROPOSAL_DECISION_HISTORY[entry.decision] if isinstance(entry, ProposalDecisionEntry) else entry_text(entry)
        )
        for entry in session.transcript
    )
    total += sum(_text_bytes(text) for text in session.queued_steering)
    total += sum(len(upload.data) for upload in session.uploads.values())
    return total + sum(map(len, session.downloads.values()))


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


class SessionStore:
    """Bounded session state. Synchronous transitions run on the owning event loop."""

    def __init__(self, settings: AiSettings, *, event_stream: SessionEventStream | None = None) -> None:
        self._event_stream = event_stream
        self._settings = settings
        self._sessions: dict[str, AgentSession] = {}
        self._retained_bytes = 0
        self._session_bytes: dict[str, int] = {}
        self._on_retire: Callable[[str], None] | None = None
        self._on_entry: Callable[[str, EntryRow], None] | None = None
        self._evictable: Callable[[str], bool] | None = None

    def on_retire(self, callback: Callable[[str], None]) -> None:
        """Register the cleanup that follows every dropped session."""
        self._on_retire = callback

    def on_entry(self, callback: Callable[[str, EntryRow], None]) -> None:
        """Register the storage that receives each new conversation entry of every session."""
        self._on_entry = callback

    def allow_eviction(self, evictable: Callable[[str], bool]) -> None:
        """Let a full store unload idle sessions that recovery storage can restore."""
        self._evictable = evictable

    def _make_room(self) -> None:
        """Unload the least recently used idle session at the session limit.

        Sessions live for the whole recovery period, so without eviction a month of chats
        would hold every slot. The unloaded session loses only its uploads, downloads, and
        finished optimizer results, as after a restart.
        """
        if self._evictable is None or len(self._sessions) < self._settings.max_sessions:
            return
        idle = [session for session in self._sessions.values() if not session.active and self._evictable(session.id)]
        if idle:
            self._retire(min(idle, key=lambda session: session.last_used).id)

    @property
    def retained_bytes(self) -> int:
        """Return the text and file bytes retained across live sessions."""
        return self._retained_bytes

    def _recount(self, session: AgentSession) -> None:
        """Refresh one session's contribution to the retained total."""
        previous = self._session_bytes.get(session.id, 0)
        current = _session_bytes(session)
        self._session_bytes[session.id] = current
        self._retained_bytes += current - previous

    def _charge(self, session: AgentSession, delta: int) -> None:
        """Apply a known size change to one session's contribution.

        Cheaper than `_recount`, which re-encodes the whole history while every session
        waits on the event loop.
        """
        self._session_bytes[session.id] += delta
        self._retained_bytes += delta

    def _forget(self, session_id: str) -> None:
        """Drop one session's contribution to the retained total."""
        self._retained_bytes -= self._session_bytes.pop(session_id, 0)

    def _require_capacity(self, additional_bytes: int) -> None:
        """Refuse content that would push retained session state past the configured budget.

        Checked where a client pushes new text or files. A completed run is never refused here,
        because its answer has already streamed to the user; `_trim_history_to_budget`
        reclaims the space instead.

        Raises:
            HTTPException: With status 429 when the budget is exhausted.
        """
        if self._retained_bytes + additional_bytes > self._settings.max_session_bytes:
            raise HTTPException(status_code=429, detail=SESSION_RETENTION_LIMIT_MESSAGE)

    def _trim_history_to_budget(self, session: AgentSession, protected_messages: int) -> None:
        """Drop this session's oldest context until retained text fits the budget.

        A run adds output without another capacity check. Initially small sessions
        would otherwise accumulate answers and proposals far past the budget and
        hold them until they expire. Older context is the part a later run needs least,
        and the message cap already truncates from the same end.

        Keep the entire completed run so its answer still has the question and any
        steering that produced it. Retained text therefore settles at the budget plus
        one run and any pending proposal per session.
        """
        while self._retained_bytes > self._settings.max_session_bytes:
            removed = self._drop_oldest_exchange(session, protected_messages)
            if not removed:
                break
            self._charge(session, -sum(_text_bytes(entry_text(entry)) for entry in removed))

    @staticmethod
    def _drop_oldest_exchange(session: AgentSession, keep_entries: int = 0) -> list[AgentMessage]:
        """Drop the oldest prompt or app event with everything that answers or decides on it.

        The newest exchange and the newest `keep_entries` entries always stay, and the
        transcript still starts at a prompt or app event, so no answer or decision is left orphaned.
        """
        transcript = session.transcript
        end = next((index for index in range(1, len(transcript)) if starts_exchange(transcript[index])), None)
        if end is None or len(transcript) - end < keep_entries:
            return []
        removed = transcript[:end]
        del transcript[:end]
        session.dropped_entries += end
        session.dropped_history_messages += len(projected_history(removed))
        return removed

    def _cap_history(self, session: AgentSession) -> None:
        """Limit retained history to the configured message count, one whole exchange at a time.

        Past the prompt history budget, drop the oldest exchanges until half the budget remains.
        Cutting in large steps keeps the prompt prefix unchanged for many runs, so the provider
        can reuse its cache. Cutting one exchange per run would change the prefix every time.
        """
        limit = max(2, self._settings.max_history_messages)
        while len(projected_history(session.transcript)) > limit and self._drop_oldest_exchange(session):
            pass
        max_chars = self._settings.max_history_chars
        if history_chars(projected_history(session.transcript)) > max_chars:
            # The newest exchange always stays. Per-request projection covers what still overflows.
            while history_chars(projected_history(session.transcript)) > max_chars // 2 and self._drop_oldest_exchange(
                session
            ):
                pass

    def create(self, owner_token: str, schedule_yaml: str) -> AgentSession:
        """Create a session after pruning expired entries."""
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
            event_stream=self._event_stream,
            entry_log=self._on_entry,
        )
        self._sessions[session.id] = session
        self._recount(session)
        return session

    def recovery_state(self, session_id: str) -> tuple[str, float, dict[str, Any]]:
        """Capture the owner, wall-clock expiry, and state that restore needs."""
        session = self._sessions[session_id]
        expires_at = time.time() + max(0.0, session.expires_at - time.monotonic())
        return session.owner_token, expires_at, session.recovery_state()

    def restore(
        self,
        session_id: str,
        owner_token: str,
        state: dict[str, Any],
        expires_at: float,
        *,
        entries: Sequence[AgentMessage],
        next_entry_seq: int,
    ) -> AgentSession:
        """Load a saved session and its rebuilt conversation with the stored expiry.

        Raises:
            HTTPException: With status 404 when it expired, or 429 when no slot or retention budget is free.
        """
        self._prune_expired()
        remaining = expires_at - time.time()
        if remaining <= 0:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        self._make_room()
        if len(self._sessions) >= self._settings.max_sessions:
            raise HTTPException(status_code=429, detail="The AI service has reached its session limit.")
        session = AgentSession.restored(
            session_id,
            owner_token,
            time.monotonic() + remaining,
            state,
            entries=entries,
            next_entry_seq=next_entry_seq,
            event_stream=self._event_stream,
            entry_log=self._on_entry,
        )
        self._require_capacity(_session_bytes(session))
        self._sessions[session_id] = session
        self._recount(session)
        return session

    def discard(self, session_id: str) -> None:
        """Drop a session that was never handed to a client."""
        if session_id in self._sessions:
            self._retire(session_id)

    def begin(self, session_id: str, owner_token: str | None, *, run_id: str | None = None) -> RunSnapshot:
        """Reserve the current conversation version for one foreground run."""
        session = self._get_owned(session_id, owner_token)
        if session.active:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        return self._reserve(session, accepting_steering=True, run_id=run_id)

    def begin_background(self, session_id: str, *, run_id: str | None = None) -> RunSnapshot | None:
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None or session.active:
            return None
        return self._reserve(session, accepting_steering=False, run_id=run_id)

    def _reserve(self, session: AgentSession, *, accepting_steering: bool, run_id: str | None) -> RunSnapshot:
        snapshot = session.begin_run(accepting_steering=accepting_steering, run_id=run_id)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        return snapshot

    def get(self, session_id: str) -> AgentSession | None:
        """Return a retained session for service-internal work that has no browser owner."""
        return self._sessions.get(session_id)

    def require_owned(self, session_id: str, owner_token: str | None) -> AgentSession:
        """Resolve a session after validating browser ownership."""
        return self._get_owned(session_id, owner_token)

    def status(self, session_id: str, owner_token: str | None) -> int:
        """Return the remaining lifetime without extending the session."""
        session = self._get_owned(session_id, owner_token)
        return max(1, math.ceil(session.expires_at - time.monotonic()))

    def finish(
        self,
        session_id: str,
        entries: Sequence[AgentMessage],
        proposal: tuple[str, str] | None = None,
        *,
        snapshot: RunSnapshot,
    ) -> RunCompletion:
        """Commit through the live session, then apply service retention limits."""
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None:
            return RunCompletion(False, False)
        completion = session.finish_run(snapshot, entries, proposal)
        if completion.run_saved:
            self._cap_history(session)
        self._recount(session)
        if not completion.run_saved:
            return completion
        self._trim_history_to_budget(session, min(len(entries), len(session.transcript)))
        history = project_history(session.transcript, self._settings.max_history_chars)
        return replace(
            completion,
            # Count retained-history and prompt-budget omissions together, in messages.
            history_trimmed_count=session.dropped_history_messages + history.dropped_messages,
            context_used_chars=history.used_chars,
        )

    def queue_steering(
        self,
        session_id: str,
        owner_token: str | None,
        message_id: str,
        message: str,
    ) -> None:
        """Queue a message for the next model boundary of an active response."""
        session = self._get_owned(session_id, owner_token)
        if not session.check_steering(message_id, self._settings.max_history_messages):
            return
        message_bytes = _text_bytes(message)
        self._require_capacity(message_bytes)
        session.steer(message_id, message)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        self._charge(session, message_bytes)

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]:
        """Drain queued messages and close the final race when a response is done."""
        session = self._sessions.get(session_id)
        if session is None:
            return []
        queued = session.take_steering(close_if_empty)
        self._charge(session, -sum(_text_bytes(text) for _message_id, text in queued))
        return queued

    def update_schedule(self, session_id: str, owner_token: str | None, schedule_yaml: str) -> None:
        """Replace the schedule snapshot, which drops any proposal made against the old one."""
        session = self._get_owned(session_id, owner_token)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        if session.schedule_yaml == schedule_yaml:
            return
        additional_bytes = (
            _text_bytes(schedule_yaml) - _text_bytes(session.schedule_yaml) - _proposal_bytes(session.pending_proposal)
        )
        if additional_bytes > 0:
            self._require_capacity(additional_bytes)
        session.update_schedule(schedule_yaml)
        self._cap_history(session)
        self._recount(session)

    def retain_uploads(
        self, session_id: str, owner_token: str | None, uploads: Sequence[SandboxAttachment]
    ) -> tuple[SandboxAttachment, ...]:
        """Retain new uploads between runs without replacing a file a message may reference."""
        session = self._get_owned(session_id, owner_token)
        session.require_idle("uploading files")
        if len(session.uploads) + len(uploads) > self._settings.max_attachment_files:
            raise HTTPException(status_code=413, detail="Too many retained files. Remove unused uploads first.")
        filenames = {item.filename for item in session.uploads.values()}
        retained = []
        for upload in uploads:
            filename = _unique_filename(upload.filename, filenames)
            filenames.add(filename)
            retained.append(replace(upload, filename=filename, id=str(uuid4())))
        event = upload_event(retained, len(session.uploads) + 1)
        self._require_capacity(sum(len(upload.data) for upload in retained) + _text_bytes(event))
        session.add_uploads(retained, event)
        self._cap_history(session)
        self._recount(session)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        return tuple(retained)

    def attachments(self, session_id: str, owner_token: str | None) -> tuple[SandboxAttachment, ...]:
        """List the retained source files of an owned session."""
        return tuple(self._get_owned(session_id, owner_token).uploads.values())

    def remove_upload(self, session_id: str, owner_token: str | None, upload_id: str) -> None:
        """Remove an unused source file between runs and reclaim its bytes."""
        session = self._get_owned(session_id, owner_token)
        session.require_idle("removing files")
        session.remove_upload(upload_id)
        self._cap_history(session)
        self._recount(session)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

    def save_download(self, session_id: str, download_id: str, content: bytes) -> bool:
        """Retain a bounded generated ZIP within the existing session retention budget."""
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None or len(content) > self._settings.max_download_bytes:
            return False
        delta = len(content) - len(session.downloads.get(download_id, b""))
        if self._retained_bytes + delta > self._settings.max_session_bytes:
            return False
        session.downloads[download_id] = content
        self._charge(session, delta)
        return True

    def download(self, session_id: str, owner_token: str | None, download_id: str) -> bytes:
        """Read a generated ZIP only for its owning browser."""
        session = self._get_owned(session_id, owner_token)
        try:
            return session.downloads[download_id]
        except KeyError:
            raise HTTPException(status_code=404, detail="This generated ZIP is no longer available.") from None

    def remove_download(self, session_id: str, owner_token: str | None, download_id: str) -> None:
        """Remove an owned generated ZIP and reclaim its bytes."""
        session = self._get_owned(session_id, owner_token)
        try:
            content = session.downloads.pop(download_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="This generated ZIP is no longer available.") from None
        self._charge(session, -len(content))
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds

    def approve_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> str | None:
        """Check ownership, decide the proposal, and account for every mutation.

        Returns the adopted schedule, or None when trusted validation refused the proposal.
        """
        session = self._get_owned(session_id, owner_token)
        try:
            approved = session.approve_proposal(base_sha256, self._settings.max_schedule_bytes)
            self._cap_history(session)
            session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
            return approved
        finally:
            # A stale revision discards the proposal before raising HTTP 409.
            self._recount(session)

    def discard_proposal(
        self,
        session_id: str,
        owner_token: str | None,
        decision: ProposalDecision = "rejected",
    ) -> None:
        """Record a proposal decision and apply service retention limits."""
        session = self._get_owned(session_id, owner_token)
        session.discard_proposal(decision)
        self._cap_history(session)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        self._recount(session)

    def abort(self, session_id: str, snapshot: RunSnapshot) -> None:
        """Release an owned reservation and its accounted steering messages."""
        session = self._sessions.get(session_id)
        if session is not None and session.abort_run(snapshot):
            self._recount(session)

    def _get_owned(self, session_id: str, owner_token: str | None) -> AgentSession:
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None or owner_token is None or session.owner_token != owner_token:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        session.last_used = time.monotonic()
        return session

    def _retire(self, session_id: str) -> None:
        """Drop one session and everything keyed by it."""
        self._sessions.pop(session_id).close_events()
        self._forget(session_id)
        if self._on_retire is not None:
            self._on_retire(session_id)

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired_ids = [session_id for session_id, session in self._sessions.items() if session.expires_at <= now]
        for session_id in expired_ids:
            self._retire(session_id)
