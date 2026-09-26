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
from uuid import uuid4

from fastapi import HTTPException

from .agent_session import (
    PROPOSAL_APPROVED_HISTORY,
    PROPOSAL_INVALID_HISTORY,
    PROPOSAL_REJECTED_HISTORY,
    AgentSession,
    RunCompletion,
    schedule_revision,
)
from .config import AiSettings
from .context import recent_history
from .lifecycle import RunSnapshot
from .provider import ChatMessage

__all__ = [
    "PROPOSAL_APPROVED_HISTORY",
    "PROPOSAL_INVALID_HISTORY",
    "PROPOSAL_REJECTED_HISTORY",
    "SessionStore",
    "schedule_revision",
]

SESSION_MEMORY_LIMIT_MESSAGE = "The AI service has reached its memory limit."


def _text_bytes(value: object) -> int:
    """Return the UTF-8 size of one chat content value, ignoring inline image data."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, list):
        return sum(len(part.get("text", "").encode("utf-8")) for part in value if part.get("type") == "text")
    return 0


def _session_bytes(session: "AgentSession") -> int:
    """Return the chat text one session retains."""
    total = _text_bytes(session.schedule_yaml) + _text_bytes(session.proposal_yaml) + _text_bytes(session.proposal_diff)
    total += sum(_text_bytes(message.get("content")) for message in session.history)
    if session.snapshot is not None:
        total += sum(_text_bytes(text) for _message_id, text in session.agent.steering_queue)
    return total


class SessionStore:
    """Bounded session state. Synchronous transitions run on the owning event loop."""

    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, AgentSession] = {}
        self._retained_bytes = 0
        self._session_bytes: dict[str, int] = {}
        self._on_retire: Callable[[str], None] | None = None

    def on_retire(self, callback: Callable[[str], None]) -> None:
        """Register the cleanup that follows every dropped session."""
        self._on_retire = callback

    @property
    def retained_bytes(self) -> int:
        """Return the chat text retained across live sessions."""
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
        """Refuse text that would push retained chat state past the configured budget.

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

        A run grows a session without passing an admission check, so sessions admitted
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

    def _effective_trimmed_count(self, session: AgentSession) -> int:
        """Count retained-history and prompt-budget omissions visible to a client."""
        return (
            session.dropped_history_messages
            + len(session.history)
            - len(recent_history(session.history, self._settings.max_history_chars))
        )

    def _cap_history(self, session: AgentSession) -> None:
        """Limit retained messages without leaving an assistant reply at the front."""
        overflow = max(0, len(session.history) - max(2, self._settings.max_history_messages))
        if overflow:
            while overflow < len(session.history) and session.history[overflow]["role"] != "user":
                overflow += 1
            del session.history[:overflow]
            session.dropped_history_messages += overflow

    def create(self, owner_token: str, schedule_yaml: str) -> AgentSession:
        """Create a session after pruning expired entries."""
        self._prune_expired()
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

    def begin(self, session_id: str, owner_token: str | None) -> RunSnapshot:
        """Reserve the current conversation version for one foreground run."""
        session = self._get_owned(session_id, owner_token)
        if session.active:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        return self._reserve(session, accepting_steering=True)

    def begin_background(self, session_id: str) -> RunSnapshot | None:
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None or session.active:
            return None
        return self._reserve(session, accepting_steering=False)

    def _reserve(self, session: AgentSession, *, accepting_steering: bool) -> RunSnapshot:
        snapshot = session.begin_run(accepting_steering=accepting_steering)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        return snapshot

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
        user_message: str,
        assistant_message: str,
        proposal: tuple[str, str] | None = None,
        *,
        snapshot: RunSnapshot,
        run_messages: Sequence[ChatMessage] = (),
    ) -> RunCompletion:
        """Commit through the live session, then apply service retention limits."""
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None:
            return RunCompletion(False, False)
        messages = run_messages or (
            ChatMessage(role="user", content=user_message),
            ChatMessage(role="assistant", content=assistant_message),
        )
        completion = session.finish_run(snapshot, messages, proposal)
        if completion.run_saved:
            self._cap_history(session)
        self._recount(session)
        if not completion.run_saved:
            return completion
        self._trim_history_to_budget(session, min(len(messages), len(session.history)))
        return replace(completion, history_trimmed_count=self._effective_trimmed_count(session))

    def queue_steering(
        self,
        session_id: str,
        owner_token: str | None,
        message_id: str,
        message: str,
    ) -> None:
        """Queue a message for the next model boundary of an active response."""
        session = self._get_owned(session_id, owner_token)
        agent = session.agent
        if not session.active or not agent.accepting_steering:
            raise HTTPException(status_code=409, detail="The active response is no longer accepting messages.")
        if message_id in agent.steering_ids:
            return
        # Counted over the whole run, not the drained queue, because the seen-ID set
        # that makes a retried POST idempotent is never emptied mid-run.
        if len(agent.steering_ids) >= self._settings.max_history_messages:
            raise HTTPException(status_code=429, detail="Too many messages are already queued.")
        message_bytes = _text_bytes(message)
        self._require_capacity(message_bytes)
        agent.steer(message_id, message)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        self._charge(session, message_bytes)

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]:
        """Drain queued messages and close the final race when a response is done."""
        session = self._sessions.get(session_id)
        if session is None or not session.active:
            return []
        queued = session.agent.take_steering(close_if_empty)
        self._charge(session, -sum(_text_bytes(text) for _message_id, text in queued))
        return queued

    def update_schedule(self, session_id: str, owner_token: str | None, schedule_yaml: str) -> None:
        """Replace the schedule snapshot, which drops any proposal made against the old one."""
        session = self._get_owned(session_id, owner_token)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        if session.schedule_yaml == schedule_yaml:
            return
        additional_bytes = (
            _text_bytes(schedule_yaml)
            - _text_bytes(session.schedule_yaml)
            - _text_bytes(session.proposal_yaml)
            - _text_bytes(session.proposal_diff)
        )
        if additional_bytes > 0:
            self._require_capacity(additional_bytes)
        session.update_schedule(schedule_yaml)
        self._recount(session)

    def peek_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> tuple[str, str]:
        """Return the pending proposal and the schedule it would replace, without adopting it."""
        session = self._require_approvable(session_id, owner_token, base_sha256)
        return session.proposal_yaml, session.schedule_yaml

    def adopt_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> str:
        """Adopt a revalidated proposal through its owner and apply retention limits."""
        session = self._require_approvable(session_id, owner_token, base_sha256)
        approved = session.adopt_proposal(base_sha256)
        self._cap_history(session)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        self._recount(session)
        return approved

    def _require_approvable(self, session_id: str, owner_token: str | None, base_sha256: str) -> AgentSession:
        """Resolve an owned proposal and account for invalidation on a stale revision."""
        session = self._get_owned(session_id, owner_token)
        try:
            session.require_proposal(base_sha256)
        finally:
            self._recount(session)
        return session

    def discard_proposal(
        self,
        session_id: str,
        owner_token: str | None,
        history_event: str = PROPOSAL_REJECTED_HISTORY,
    ) -> None:
        """Record a proposal decision and apply service retention limits."""
        session = self._get_owned(session_id, owner_token)
        session.discard_proposal(history_event)
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
        return session

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired_ids = [session_id for session_id, session in self._sessions.items() if session.expires_at <= now]
        for session_id in expired_ids:
            del self._sessions[session_id]
            self._forget(session_id)
            if self._on_retire is not None:
                self._on_retire(session_id)
