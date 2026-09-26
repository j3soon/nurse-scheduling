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

import hashlib
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import HTTPException

from .background import recent_history
from .config import AiSettings
from .lifecycle import RunSnapshot
from .provider import ChatMessage

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
    dropped_history_messages: int = 0
    version: int = 0
    turn: RunSnapshot | None = None
    proposal_yaml: str = ""
    proposal_diff: str = ""

    @property
    def active(self) -> bool:
        return self.turn is not None


SESSION_MEMORY_LIMIT_MESSAGE = "The AI service has reached its memory limit."


def _text_bytes(value: object) -> int:
    """Return the UTF-8 size of one chat content value, ignoring inline image data."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, list):
        return sum(len(part.get("text", "").encode("utf-8")) for part in value if part.get("type") == "text")
    return 0


def _session_bytes(session: "ChatSession") -> int:
    """Return the chat text one session retains."""
    total = _text_bytes(session.schedule_yaml) + _text_bytes(session.proposal_yaml) + _text_bytes(session.proposal_diff)
    total += sum(_text_bytes(message.get("content")) for message in session.history)
    if session.turn is not None:
        total += sum(_text_bytes(text) for _message_id, text in session.turn.steering_queue)
    return total


@dataclass(frozen=True)
class RunCompletion:
    """Whether a completed turn and its optional proposal were retained."""

    turn_saved: bool
    proposal_saved: bool
    history_trimmed_count: int = 0


class SessionStore:
    """Bounded session state. Synchronous transitions run on the owning event loop."""

    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, ChatSession] = {}
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

    def _recount(self, session: ChatSession) -> None:
        """Refresh one session's contribution to the retained total."""
        previous = self._session_bytes.get(session.id, 0)
        current = _session_bytes(session)
        self._session_bytes[session.id] = current
        self._retained_bytes += current - previous

    def _charge(self, session: ChatSession, delta: int) -> None:
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

    def begin(self, session_id: str, owner_token: str | None) -> RunSnapshot:
        """Reserve the current conversation version for one foreground turn."""
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

    def _reserve(self, session: ChatSession, *, accepting_steering: bool) -> RunSnapshot:
        session.turn = RunSnapshot(
            list(session.history),
            session.schedule_yaml,
            session.version,
            session.proposal_yaml,
            session.proposal_diff,
            accepting_steering,
            previously_dropped=session.dropped_history_messages,
        )
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        return session.turn

    def require_owned(self, session_id: str, owner_token: str | None) -> None:
        """Validate access to a session without exposing its state."""
        self._get_owned(session_id, owner_token)

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
        turn_messages: Sequence[ChatMessage] = (),
    ) -> RunCompletion:
        """Save a completed turn when its schedule revision is still current."""
        self._prune_expired()
        session = self._sessions.get(session_id)
        if session is None or session.turn is not snapshot:
            return RunCompletion(turn_saved=False, proposal_saved=False)
        session.turn = None
        if session.version != snapshot.version:
            self._recount(session)
            return RunCompletion(turn_saved=False, proposal_saved=False)
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
        return RunCompletion(
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
        session.version += 1
        session.schedule_yaml = schedule_yaml
        session.revision = schedule_revision(schedule_yaml)
        session.proposal_yaml = ""
        session.proposal_diff = ""
        self._recount(session)

    def peek_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> tuple[str, str]:
        """Return the pending proposal and the schedule it would replace, without adopting it."""
        session = self._require_approvable(session_id, owner_token, base_sha256)
        return session.proposal_yaml, session.schedule_yaml

    def adopt_proposal(self, session_id: str, owner_token: str | None, base_sha256: str) -> str:
        """Adopt a revalidated proposal as the session schedule and record the approval."""
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
        session = self._get_owned(session_id, owner_token)
        had_proposal = bool(session.proposal_yaml)
        session.proposal_yaml = ""
        session.proposal_diff = ""
        if had_proposal:
            session.version += 1
            self._append_history_event(session, history_event)
        session.expires_at = time.monotonic() + self._settings.session_ttl_seconds
        self._recount(session)

    def abort(self, session_id: str, snapshot: RunSnapshot) -> None:
        """Only the owner of a reservation may release it."""
        session = self._sessions.get(session_id)
        if session is not None and session.turn is snapshot:
            session.turn = None
            self._recount(session)

    def _append_history_event(self, session: ChatSession, content: str) -> None:
        """Append one trusted application event within the retention bound."""
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
