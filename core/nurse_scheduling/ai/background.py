"""Replayable events and agent turns triggered by background work."""

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
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from dataclasses import asdict, dataclass
from typing import Protocol

from .agent_types import AgentProposal, AgentReasoning, AgentText, AgentToolStart, AgentToolUse
from .config import DEFAULT_MAX_HISTORY_CHARS, AiSettings
from .history import ChatHistory
from .lifecycle import Turn, TurnSnapshot
from .optimizer import WORKSPACE_OPTIMIZER_RESULT, OptimizerArtifact, SessionOptimizer
from .provider import ChatMessage, ProviderError, TokenUsage, ToolCapableChatProvider
from .sandbox import SandboxError, SandboxFactory
from .schedule_context import describe_schedule
from .turns import append_compacted
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
    attachment_path,
)
from .workspace_tools import run_workspace

CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent turn were "
    "discarded. The current schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_COMMAND_TIMEOUT_ERROR = (
    "An AI shell command timed out. The temporary workspace was discarded. Please try again."
)
SANDBOX_TURN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_TURN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
logger = logging.getLogger("nurse_scheduling.ai")


class TurnCompletion(Protocol):
    """Result fields used by background turn finalization."""

    turn_saved: bool
    proposal_saved: bool
    history_trimmed_count: int
    context_used_chars: int


class BackgroundSessionStore(Protocol):
    """Session operations needed by a trusted background turn."""

    def begin_background(self, session_id: str) -> TurnSnapshot | None: ...

    def finish(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        proposal: tuple[str, str] | None = None,
        *,
        snapshot: TurnSnapshot,
        turn_messages: Sequence[ChatMessage] = (),
    ) -> TurnCompletion: ...

    def abort(self, session_id: str, snapshot: TurnSnapshot) -> None: ...

    def attachments(self, session_id: str) -> tuple[SandboxAttachment, ...]: ...

    def save_download(self, session_id: str, download_id: str, content: bytes) -> bool: ...


@dataclass(frozen=True)
class SessionEvent:
    """One replayable event from an assistant turn initiated by background work."""

    id: int
    type: str
    data: dict[str, object]


class SessionEventBroker:
    """Process-local replay for background turns and independent optimizer progress."""

    def __init__(
        self,
        max_events_per_session: int = 1000,
        max_sessions: int = 1000,
        max_progress_events_per_session: int = 100,
        max_snapshot_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self._max_events_per_session = max_events_per_session
        self._max_progress_events_per_session = max_progress_events_per_session
        self._max_sessions = max_sessions
        self._events: dict[str, list[SessionEvent]] = {}
        self._progress_events: dict[str, list[SessionEvent]] = {}
        self._last_ids: dict[str, int] = {}
        self._signals: dict[str, asyncio.Event] = {}
        self._snapshots: dict[str, list[dict]] = {}
        self._evicted_ids: dict[str, int] = {}
        self._publish_locks: dict[str, asyncio.Lock] = {}
        self.on_publish = None
        self.load_snapshot = None
        self._snapshot_incomplete: set[str] = set()
        self._snapshot_bytes: dict[str, int] = {}
        self._max_snapshot_bytes = max_snapshot_bytes

    async def emit(
        self, session_id: str, event_type: str, data: dict[str, object], *, metadata: dict | None = None
    ) -> None:
        lock = self._publish_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            if self._publish_locks.get(session_id) is not lock:
                return
            event_id = self._last_ids.get(session_id, 0) + 1
            if self.on_publish is not None and event_type != "optimization_progress":
                if metadata is None:
                    await self.on_publish(session_id, event_id, event_type, data)
                else:
                    await self.on_publish(session_id, event_id, event_type, data, metadata)
            if self._publish_locks.get(session_id) is lock:
                self.publish(session_id, event_type, data)

    def publish(self, session_id: str, event_type: str, data: dict[str, object]) -> None:
        if session_id not in self._events and len(self._events) >= self._max_sessions:
            oldest_session_id = next(iter(self._events))
            self.forget_session(oldest_session_id)
        self._events.setdefault(session_id, [])
        events = (
            self._progress_events.setdefault(session_id, [])
            if event_type == "optimization_progress"
            else self._events[session_id]
        )
        event_id = self._last_ids.get(session_id, 0) + 1
        self._last_ids[session_id] = event_id
        events.append(SessionEvent(event_id, event_type, data))
        if event_type != "optimization_progress" and session_id not in self._snapshot_incomplete:
            append_compacted(self._snapshots.setdefault(session_id, []), event_type, data)
            self._snapshot_bytes[session_id] = self._snapshot_bytes.get(session_id, 0) + len(json.dumps(data).encode())
            if sum(self._snapshot_bytes.values()) > self._max_snapshot_bytes:
                if self.load_snapshot is not None:
                    self._snapshots.pop(session_id, None)
                    self._snapshot_bytes.pop(session_id, None)
                    self._snapshot_incomplete.add(session_id)
                else:
                    self._trim_snapshot(session_id)
        limit = (
            self._max_progress_events_per_session
            if event_type == "optimization_progress"
            else self._max_events_per_session
        )
        if event_type != "optimization_progress" and len(events) > limit:
            self._evicted_ids[session_id] = max(self._evicted_ids.get(session_id, 0), events[-limit - 1].id)
        del events[:-limit]
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def _trim_snapshot(self, session_id: str) -> None:
        """Without recovery storage, drop a session's oldest output until the snapshots fit.

        Trim to three quarters of the budget, so a full cache does not measure the
        snapshot again on every event.
        """
        snapshot = self._snapshots[session_id]
        sizes = [len(json.dumps(entry["data"]).encode()) for entry in snapshot]
        others = sum(self._snapshot_bytes.values()) - self._snapshot_bytes[session_id]
        retained = sum(sizes)
        dropped = 0
        while dropped < len(sizes) - 1 and others + retained > self._max_snapshot_bytes * 3 // 4:
            retained -= sizes[dropped]
            dropped += 1
        del snapshot[:dropped]
        self._snapshot_bytes[session_id] = retained

    def forget_session(self, session_id: str) -> None:
        self._events.pop(session_id, None)
        self._progress_events.pop(session_id, None)
        self._last_ids.pop(session_id, None)
        self._snapshots.pop(session_id, None)
        self._snapshot_bytes.pop(session_id, None)
        self._snapshot_incomplete.discard(session_id)
        self._evicted_ids.pop(session_id, None)
        self._publish_locks.pop(session_id, None)
        # Wake an open stream so it observes the dropped signal and ends, instead of
        # recreating the entry this pop removes and waiting on a retired session.
        signal = self._signals.pop(session_id, None)
        if signal is not None:
            signal.set()

    def restore(self, session_id: str, events: list[dict]) -> None:
        if events and events[0].get("first_id", events[0]["id"]) > 1:
            self._snapshot_incomplete.add(session_id)
            self._evicted_ids[session_id] = events[0]["id"] - 1
        for event in events:
            self._last_ids[session_id] = event["id"] - 1
            self.publish(session_id, event["type"], event["data"])
        if events:
            # Recovery entries contain accumulated text, so replay them as a replacement.
            self._evicted_ids[session_id] = events[-1]["id"]

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Return retained events after a cursor for replay and diagnostics."""
        retained = (*self._events.get(session_id, ()), *self._progress_events.get(session_id, ()))
        return tuple(sorted((event for event in retained if event.id > after_id), key=lambda event: event.id))

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        signal = self._signals.setdefault(session_id, asyncio.Event())
        while True:
            if self._signals.get(session_id) is not signal:
                return
            if after_id < self._evicted_ids.get(session_id, 0) or after_id > self._last_ids.get(session_id, 0):
                if session_id in self._snapshot_incomplete and self.load_snapshot is not None:
                    after_id, events = await self.load_snapshot(session_id)
                else:
                    after_id = self._last_ids.get(session_id, 0)
                    events = self._snapshots.get(session_id, [])
                yield SessionEvent(after_id, "session_snapshot", {"events": events})
                continue
            pending = self.events_after(session_id, after_id)
            if pending:
                for event in pending:
                    after_id = event.id
                    yield event
                continue
            if self._signals.get(session_id) is not signal:
                return
            signal.clear()
            try:
                await asyncio.wait_for(signal.wait(), timeout=15)
            except TimeoutError:
                yield None


def recent_history(history: list[ChatMessage], max_chars: int) -> list[ChatMessage]:
    """Keep the newest retained messages that fit the prompt budget, oldest first.

    Retention bounds how much of a conversation the session holds, not how much a
    provider can accept. A long session would otherwise grow every later prompt past
    the model context window and fail the request outright.
    """
    kept: list[ChatMessage] = []
    remaining = max_chars
    for message in reversed(history):
        remaining -= len(json.dumps(message, ensure_ascii=False))
        if remaining < 0:
            break
        kept.append(message)
    kept.reverse()
    return kept


APP_EVENT_PREFIX = "[App event]"
STATUS_PREFIX = "[Current status]"
SCHEDULE_CHANGED_EVENT = (
    f"{APP_EVENT_PREFIX} The schedule changed in the app. /workspace/schedule.yaml contains the current version."
)
SCHEDULE_CHANGED_DISCARDED_EVENT = (
    f"{SCHEDULE_CHANGED_EVENT} The pending proposal was discarded because it was made for the previous schedule."
)
PROPOSAL_APPROVED_HISTORY = (
    f"{APP_EVENT_PREFIX} The user approved the previous schedule proposal. Its changes are now part of the current "
    "schedule."
)
PROPOSAL_REJECTED_HISTORY = (
    f"{APP_EVENT_PREFIX} The user rejected the previous schedule proposal. All schedule changes made during that agent "
    "turn were discarded. This turn starts with a fresh workspace containing the current schedule."
)
PROPOSAL_INVALID_HISTORY = (
    f"{APP_EVENT_PREFIX} The previous schedule proposal failed trusted validation when the user approved it, so it was "
    "discarded. All schedule changes made during that agent turn were dropped. This turn starts with a fresh "
    "workspace containing the current schedule."
)
UPLOAD_EVENT_PREFIX = f"{APP_EVENT_PREFIX} The user uploaded files."
REMOVAL_EVENT_PREFIX = f"{APP_EVENT_PREFIX} The user removed a file from the workspace:"
PENDING_PROPOSAL_STATUS = (
    "A validated proposal is pending. Its exact candidate and diff are available in the trusted workspace files that "
    "the instructions describe."
)
OPTIMIZER_RESULT_STATUS = "Optimization result:"
UNLISTED_UPLOADS_STATUS = "Uploaded files not listed in this conversation:"
# Short titles let the chat label each app-written message without parsing its text.
_APP_EVENT_TITLES = (
    (UPLOAD_EVENT_PREFIX, "Files Uploaded"),
    (REMOVAL_EVENT_PREFIX, "File Removed"),
    (SCHEDULE_CHANGED_DISCARDED_EVENT, "Schedule Changed, Proposal Discarded"),
    (SCHEDULE_CHANGED_EVENT, "Schedule Changed"),
    (PROPOSAL_APPROVED_HISTORY, "Proposal Approved"),
    (PROPOSAL_REJECTED_HISTORY, "Proposal Rejected"),
    (PROPOSAL_INVALID_HISTORY, "Proposal Invalid"),
)
_STATUS_TITLES = (
    (PENDING_PROPOSAL_STATUS, "Pending Proposal"),
    (OPTIMIZER_RESULT_STATUS, "Optimizer Result"),
    (UNLISTED_UPLOADS_STATUS, "Unlisted Uploads"),
)


def history_chars(messages: Sequence[ChatMessage]) -> int:
    """Measure messages the same way the prompt history budget does."""
    return sum(len(json.dumps(message, ensure_ascii=False)) for message in messages)


def _file_entry(attachment: SandboxAttachment, index: int) -> dict[str, str | int]:
    return {
        "filename": attachment.filename,
        "path": attachment_path(attachment, index),
        "media_type": attachment.media_type,
        "bytes": len(attachment.data),
    }


def upload_event(attachments: Sequence[SandboxAttachment], first_index: int = 1) -> str:
    """Describe uploaded files once in history, so later requests keep the same prefix."""
    files = [_file_entry(attachment, index) for index, attachment in enumerate(attachments, start=first_index)]
    return (
        f"{UPLOAD_EVENT_PREFIX} They stay in the workspace until the user removes them: "
        f"{json.dumps(files, ensure_ascii=False)}"
    )


def removal_event(attachment: SandboxAttachment, index: int) -> str:
    """Describe one removed file in history."""
    removed = {"filename": attachment.filename, "path": attachment_path(attachment, index)}
    return f"{REMOVAL_EVENT_PREFIX} {json.dumps(removed, ensure_ascii=False)}"


def status_message(
    history: Sequence[ChatMessage],
    attachments: Sequence[SandboxAttachment],
    *,
    pending_proposal: bool,
    optimizer_result_available: bool,
) -> str:
    """Describe request-specific state that would otherwise change the cached prompt prefix."""
    lines = []
    if pending_proposal:
        lines.append(PENDING_PROPOSAL_STATUS)
    if optimizer_result_available:
        lines.append(f"{OPTIMIZER_RESULT_STATUS} {WORKSPACE_OPTIMIZER_RESULT}.")
    # Trimmed history or a failed turn can hide an upload event, so list only the files the request cannot show.
    sent = "\n".join(str(message["content"]) for message in history)
    unlisted = [
        entry
        for index, attachment in enumerate(attachments, start=1)
        if (entry := _file_entry(attachment, index))["path"] not in sent
    ]
    if unlisted:
        lines.append(f"{UNLISTED_UPLOADS_STATUS} {json.dumps(unlisted, ensure_ascii=False)}")
    return f"{STATUS_PREFIX}\n" + "\n".join(lines) if lines else ""


def context_usage(
    used_chars: int,
    settings: AiSettings,
    last_call: TokenUsage | None = None,
    provider: ToolCapableChatProvider | None = None,
) -> dict[str, int]:
    """Report retained history size and the latest request's tokens with the provider's context limit.

    The latest provider call holds the whole conversation that the model saw, so its prompt and
    completion tokens show how full the context window is. A sum over a turn's calls would count
    the same prompt several times.
    """
    usage = {"used_chars": used_chars, "max_chars": settings.max_history_chars}
    if last_call is not None:
        usage["used_tokens"] = last_call.prompt_tokens + last_call.completion_tokens
        limit = getattr(provider, "context_tokens", None)
        if type(limit) is int and limit > 0:
            usage["max_tokens"] = limit
    return usage


def history_context_chars(history: list[ChatMessage], max_chars: int) -> int:
    """Measure the serialized conversation selected for the next turn's history budget."""
    return history_chars(recent_history(history, max_chars))


def build_provider_messages(
    history: list[ChatMessage],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
    optimizer_result_available: bool = False,
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS,
    max_download_bytes: int = 50_000_000,
) -> list[ChatMessage]:
    """Build a provider prompt whose system message and history stay unchanged between requests.

    Providers reuse cached work only for an identical prefix. Request-specific state therefore goes
    into a final status message that history never keeps.
    """
    system_content = f"{system_prompt}\n\n{describe_schedule(schedule_yaml)}"
    system_content += f"\nDownload size limit: {max_download_bytes} bytes.\n"
    retained = recent_history(history, max_history_chars)
    status = status_message(
        retained,
        attachments,
        pending_proposal=pending_proposal,
        optimizer_result_available=optimizer_result_available,
    )
    return [
        ChatMessage(role="system", content=system_content),
        *retained,
        ChatMessage(role="user", content=question),
        *([ChatMessage(role="user", content=status)] if status else []),
    ]


def message_title(kind: str, content: str) -> str | None:
    """Name the topic of an app event or status message for its chat label."""
    if kind == "app":
        return next((title for prefix, title in _APP_EVENT_TITLES if content.startswith(prefix)), None)
    if kind == "status":
        lines = content.split("\n")[1:]
        titles = [title for prefix, title in _STATUS_TITLES if any(line.startswith(prefix) for line in lines)]
        return ", ".join(titles) or None
    return None


def model_input(
    messages: Sequence[ChatMessage], history_count: int, history_offset: int, question_kind: str
) -> dict[str, object]:
    """Describe a provider request for the chat: its system message and the messages added since the last reply.

    History messages after the last assistant reply are app events. Each one carries its absolute history
    index, so the chat shows it once even when a failed turn is retried.
    """
    history = messages[1 : 1 + history_count]
    last_reply = max((index for index, message in enumerate(history) if message["role"] == "assistant"), default=-1)
    added: list[dict[str, object]] = [
        {"kind": "app", "index": history_offset + index, "content": message["content"]}
        for index, message in enumerate(history)
        if index > last_reply
    ]
    added.append({"kind": question_kind, "content": messages[1 + history_count]["content"]})
    added.extend({"kind": "status", "content": message["content"]} for message in messages[2 + history_count :])
    for entry in added:
        if title := message_title(str(entry["kind"]), str(entry["content"])):
            entry["title"] = title
    return {"system": messages[0]["content"], "messages": added}


async def run_background_turn(
    session_id: str,
    question: str,
    artifact: OptimizerArtifact | None,
    *,
    settings: AiSettings,
    store: BackgroundSessionStore,
    event_broker: SessionEventBroker,
    turn: Turn,
    concurrency_limit: asyncio.Semaphore,
    history_log: ChatHistory | None,
    provider: ToolCapableChatProvider,
    sandbox_factory: SandboxFactory,
    session_optimizer: SessionOptimizer,
) -> None:
    """Wake an idle agent after a background optimizer job reaches a terminal state."""
    snapshot = store.begin_background(session_id)
    if snapshot is None:
        return
    history, schedule_yaml = snapshot.history, snapshot.schedule_yaml
    proposal_yaml, proposal_diff = snapshot.proposal_yaml, snapshot.proposal_diff
    previously_dropped = snapshot.dropped_history_messages
    turn_id = turn.id
    assistant_parts: list[str] = []
    pending_proposal: AgentProposal | None = None
    pending_download: bytes | None = None
    completed = False

    error_code: str | None = "internal_error"
    usage: TokenUsage | None = None
    last_call: TokenUsage | None = None

    async def emit(event_type: str, data: dict, *, metadata: dict | None = None) -> None:
        if not turn.retired:
            await event_broker.emit(session_id, event_type, {**data, "turn_id": turn.id}, metadata=metadata)

    async def emit_terminal(event_type: str, data: dict) -> None:
        turn.finishing = True
        if turn.retired:
            return
        if not completed:
            store.abort(session_id, snapshot)
        await emit(
            event_type,
            data,
            metadata={
                "error_code": error_code,
                "usage": asdict(usage) if usage else None,
            },
        )

    try:
        turn.admitting = True
        try:
            if history_log is not None and not await history_log.write(
                "start_recovery_turn",
                turn_id,
                session_id,
                None,
                question,
                {
                    "kind": "background",
                    "model": settings.provider_model,
                    "attachment_count": len(store.attachments(session_id)),
                },
            ):
                store.abort(session_id, snapshot)
                await emit(
                    "error",
                    {"message": "AI message recovery is unavailable, so the optimizer result was not reviewed."},
                )
                return
        finally:
            turn.admitting = False
        if turn.cancelled:
            raise asyncio.CancelledError
        # A failed recovery write raises from emit, so the turn must already release the session.
        await emit("turn_start", {"message_id": turn_id, "trigger": "optimizer"})
        context_chars = history_context_chars(history, settings.max_history_chars)
        await emit("context_usage", context_usage(context_chars, settings))
        retained_history = recent_history(history, settings.max_history_chars)
        dropped_history = previously_dropped + len(history) - len(retained_history)
        if dropped_history:
            await emit(
                "history_trimmed",
                {"dropped": dropped_history},
            )
        attachments = store.attachments(session_id)
        messages = build_provider_messages(
            retained_history,
            schedule_yaml,
            question,
            attachments,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            pending_proposal=bool(proposal_yaml),
            optimizer_result_available=artifact is not None,
            max_history_chars=settings.max_history_chars,
            max_download_bytes=settings.max_download_bytes,
        )
        await emit("model_input", model_input(messages, len(retained_history), dropped_history, "optimizer"))
        async with concurrency_limit:
            agent_events = run_workspace(
                provider,
                sandbox_factory,
                schedule_yaml,
                messages,
                WorkspaceLimits.from_settings(settings),
                pending_proposal_yaml=proposal_yaml,
                pending_proposal_diff=proposal_diff,
                execute_optimizer=(
                    lambda current_yaml, arguments: session_optimizer.execute(session_id, current_yaml, arguments)
                ),
                optimizer_result=artifact.content if artifact is not None else None,
                optimizer_context=artifact.schedule_context if artifact is not None else None,
                attachments=attachments,
            )
            async with aclosing(agent_events):
                async for event in agent_events:
                    if isinstance(event, AgentText):
                        assistant_parts.append(event.text)
                        await emit("delta", {"text": event.text})
                    elif isinstance(event, AgentReasoning):
                        await emit("reasoning", {"text": event.text})
                    elif isinstance(event, TokenUsage):
                        usage = event if usage is None else usage + event
                        last_call = event
                        await emit("context_usage", context_usage(context_chars, settings, last_call, provider))
                    elif isinstance(event, AgentToolStart):
                        await emit(
                            "tool_start",
                            {"name": event.name, "arguments": event.arguments},
                        )
                    elif isinstance(event, AgentToolUse):
                        await emit(
                            "tool",
                            {
                                "name": event.name,
                                "arguments": event.arguments,
                                "result": event.result,
                                "ok": event.ok,
                            },
                        )
                    elif isinstance(event, AgentScheduleChange):
                        await emit(
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
        completion = store.finish(
            session_id,
            question,
            "".join(assistant_parts),
            proposal,
            snapshot=snapshot,
        )
        completed = True
        turn.finishing = True
        if not completion.turn_saved:
            error_code = None
            await emit_terminal("stale", {"message": STALE_TURN_ERROR})
            return
        error_code = None
        if completion.history_trimmed_count and completion.history_trimmed_count != dropped_history:
            await emit(
                "history_trimmed",
                {"dropped": completion.history_trimmed_count},
            )
        if completion.proposal_saved and pending_proposal is not None:
            await emit("proposal", {"diff": pending_proposal.diff})
        if pending_download is not None:
            if store.save_download(session_id, turn_id, pending_download):
                await emit("download", {"download_id": turn_id})
            else:
                await emit(
                    "warning",
                    {
                        "message": "The generated ZIP could not be retained because the service memory limit was reached."
                    },
                )
        await emit("context_usage", context_usage(completion.context_used_chars, settings, last_call, provider))
        await emit_terminal("done", {"message_id": turn_id})
    except asyncio.CancelledError:
        if completed and completion.turn_saved:
            error_code = None
            await emit_terminal("done", {"message_id": turn_id})
        elif completed:
            error_code = None
            await emit_terminal("stale", {"message": STALE_TURN_ERROR})
        else:
            error_code = None
            await emit_terminal("stopped", {"message_id": turn_id})
        raise
    except ProviderError as exc:
        error_code = "provider_error"
        await emit_terminal("error", {"message": exc.user_message or PROVIDER_ERROR})
    except SandboxDownloadError as exc:
        error_code = "download_error"
        await emit_terminal("error", {"message": str(exc)})
    except SandboxCommandTimeoutError:
        error_code = "sandbox_command_timeout"
        await emit_terminal("error", {"message": SANDBOX_COMMAND_TIMEOUT_ERROR})
    except SandboxTurnTimeoutError:
        error_code = "sandbox_timeout"
        await emit_terminal("error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})
    except SandboxCandidateError as exc:
        error_code = "candidate_validation"
        await emit_terminal(
            "error",
            {"message": CANDIDATE_VALIDATION_ERROR + (f"\n\n{exc.user_message}" if exc.user_message else "")},
        )
    except SandboxError:
        error_code = "sandbox_error"
        logger.exception("Background AI sandbox turn failed session_id=%s", session_id)
        await emit_terminal(
            "error",
            {"message": "The temporary AI sandbox failed while reviewing optimizer results."},
        )
    except Exception:
        logger.exception("Unexpected background AI turn failure session_id=%s", session_id)
        await emit_terminal(
            "error",
            {"message": "The AI could not review the optimizer result."},
        )
    finally:
        if not completed:
            store.abort(session_id, snapshot)
