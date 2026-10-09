"""Application session state and execution above the agent and workspace."""

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

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import aclosing
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException
from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from .agent import Agent
from .agent_types import AgentProposal, AgentReasoning, AgentSteering, AgentText, AgentToolStart, AgentToolUse
from .candidate import validate_schedule_change
from .config import AiSettings
from .context import (
    CANDIDATE_VALIDATION_ERROR,
    PROPOSAL_INVALID_HISTORY,
    PROPOSAL_REJECTED_HISTORY,
    PROVIDER_ERROR,
    SANDBOX_COMMAND_TIMEOUT_ERROR,
    SANDBOX_TURN_TIMEOUT_ERROR,
    SCHEDULE_CHANGED_DISCARDED_EVENT,
    SCHEDULE_CHANGED_EVENT,
    STALE_TURN_ERROR,
    build_provider_messages,
    context_usage,
    interrupted_entries,
    model_input,
    project_history,
    projected_history,
)
from .lifecycle import SessionTurns, Turn, TurnSnapshot
from .optimizer import OptimizerArtifact, SessionOptimizer
from .optimizer_tool import execute_optimizer_tool
from .provider import ChatMessage, ProviderError, TokenUsage, ToolCapableChatProvider
from .recovery import SessionRecovery
from .sandbox import SandboxError, SandboxFactory
from .transcript import AgentMessage, AppEventEntry, ProposalDecisionEntry, UserMessage
from .turns import TERMINAL_EVENTS, ReplayTurn, append_compacted
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

if TYPE_CHECKING:
    from .sessions import SessionStore

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


def _schedule_data(schedule_yaml: str) -> object:
    """Parse a schedule for comparison, so a formatting-only change is not reported as an edit."""
    try:
        return _load_yaml(schedule_yaml.encode(), reject_aliases=True)
    except (ValueError, YAMLError):
        return schedule_yaml


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so a stale proposal cannot be applied."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


class ProposalValidationError(HTTPException):
    """An invalid pending proposal was discarded before it could become current."""

    def __init__(self) -> None:
        super().__init__(status_code=409, detail="The proposed schedule is no longer valid.")


@dataclass
class AgentSession:
    """Process-local conversation state owned by one browser cookie."""

    id: str
    owner_token: str
    expires_at: float
    schedule_yaml: str
    revision: str
    transcript: list[AgentMessage] = field(default_factory=list)
    dropped_history_messages: int = 0
    version: int = 0
    turn: TurnSnapshot | None = None

    proposal_yaml: str = ""
    proposal_diff: str = ""
    downloads: dict[str, bytes] = field(default_factory=dict)
    uploads: dict[str, SandboxAttachment] = field(default_factory=dict)
    last_used: float = field(default_factory=time.monotonic)
    """Last owner access, which orders eviction. A restored session keeps its stored expiry."""

    agent: Agent = field(default_factory=Agent, repr=False)

    @property
    def history(self) -> list[ChatMessage]:
        """Expose the legacy text view at the persistence compatibility boundary."""
        return projected_history(self.transcript)

    @property
    def active(self) -> bool:
        return self.turn is not None

    def begin_run(self, *, accepting_steering: bool) -> TurnSnapshot:
        if self.active:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        snapshot = TurnSnapshot(
            list(self.transcript),
            self.schedule_yaml,
            self.version,
            self.proposal_yaml,
            self.proposal_diff,
            accepting_steering,
            self.dropped_history_messages,
        )
        self.turn = snapshot
        return snapshot

    def commit_turn(
        self, snapshot: TurnSnapshot, messages: Sequence[AgentMessage], proposal: tuple[str, str] | None
    ) -> bool:
        if self.turn is not snapshot:
            return False
        self.turn = None
        if self.version != snapshot.version:
            return False
        self.transcript.extend(messages)
        if proposal is not None:
            self.proposal_yaml, self.proposal_diff = proposal
        return True

    def abort(self, snapshot: TurnSnapshot) -> None:
        if self.turn is snapshot:
            self.turn = None

    def check_steering(self, message_id: str, max_messages: int) -> bool:
        turn = self.turn
        if turn is None or not turn.accepting_steering:
            raise HTTPException(status_code=409, detail="The active response is no longer accepting messages.")
        if message_id in turn.steering_ids:
            return False
        # Seen IDs bound the whole response, including input already consumed by the model.
        if len(turn.steering_ids) >= max_messages:
            raise HTTPException(status_code=429, detail="Too many messages are already queued.")
        return True

    def queue_steering(self, message_id: str, message: str) -> None:
        self.turn.steering_queue.append((message_id, message))
        self.turn.steering_ids.add(message_id)

    def take_steering(self, close_if_empty: bool) -> list[tuple[str, str]]:
        if self.turn is None:
            return []
        queued = list(self.turn.steering_queue)
        self.turn.steering_queue.clear()
        if close_if_empty and not queued:
            self.turn.accepting_steering = False
        return queued

    def update_schedule(self, schedule_yaml: str) -> None:
        data_changed = _schedule_data(self.schedule_yaml) != _schedule_data(schedule_yaml)
        had_proposal = bool(self.proposal_yaml)
        if self.schedule_yaml != schedule_yaml or had_proposal:
            self.version += 1
        self.schedule_yaml = schedule_yaml
        self.revision = schedule_revision(schedule_yaml)
        self.proposal_yaml = ""
        self.proposal_diff = ""
        if data_changed or had_proposal:
            self.transcript.append(
                AppEventEntry(SCHEDULE_CHANGED_DISCARDED_EVENT if had_proposal else SCHEDULE_CHANGED_EVENT)
            )

    def require_proposal(self, base_sha256: str) -> None:
        if not self.proposal_yaml:
            raise HTTPException(status_code=404, detail="No proposal is waiting for approval.")
        if self.revision != base_sha256:
            self.proposal_yaml = ""
            self.proposal_diff = ""
            self.version += 1
            raise HTTPException(
                status_code=409, detail="The schedule changed after this proposal was created, so it was discarded."
            )

    def approve_proposal(self, base_sha256: str, max_bytes: int) -> str:
        self.require_proposal(base_sha256)
        _, introduced = validate_schedule_change(self.schedule_yaml, self.proposal_yaml, max_bytes)
        if introduced:
            self.discard_proposal(PROPOSAL_INVALID_HISTORY)
            raise ProposalValidationError
        approved = self.proposal_yaml
        self.proposal_yaml = ""
        self.proposal_diff = ""
        self.version += 1
        self.schedule_yaml = approved
        self.revision = schedule_revision(approved)
        self.transcript.append(ProposalDecisionEntry("approved"))
        return approved

    def discard_proposal(self, history_event: str = PROPOSAL_REJECTED_HISTORY) -> None:
        had_proposal = bool(self.proposal_yaml)
        self.proposal_yaml = ""
        self.proposal_diff = ""
        if had_proposal:
            self.version += 1
            self.transcript.append(
                ProposalDecisionEntry("invalid" if history_event == PROPOSAL_INVALID_HISTORY else "rejected")
            )

    async def accept_message(
        self,
        question: str,
        message_id: str | None,
        owner: str | None,
        credential_id: str | None,
        runtime: SessionRuntime,
    ) -> tuple[ReplayTurn, bool]:
        """Admit one question or reconnect to the already accepted response."""
        journal = runtime.recovery.turn_journal
        try:
            existing = await journal.get(self.id, message_id) if message_id is not None else None
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        if existing is not None:
            if existing.question != question:
                raise HTTPException(status_code=409, detail="This message ID belongs to a different question.")
            return existing, True
        replay: ReplayTurn | None = None

        def accepted(value: ReplayTurn) -> None:
            nonlocal replay
            replay = value

        turn = runtime.turns.start(
            self.id,
            lambda turn: self.run(
                runtime,
                turn,
                question,
                owner=owner,
                message_id=message_id,
                credential_id=credential_id,
                accepted=accepted,
            ),
            message_id=message_id,
        )
        turn.task.add_done_callback(runtime.recovery.pin_session(self.id))
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
        if replay is None:
            raise RuntimeError("The foreground response was not accepted.")
        return replay, False

    async def run(
        self,
        runtime: SessionRuntime,
        turn: Turn,
        question: str,
        *,
        background: bool = False,
        owner: str | None = None,
        message_id: str | None = None,
        credential_id: str | None = None,
        artifact: OptimizerArtifact | None = None,
        accepted: Callable[[ReplayTurn], None] | None = None,
    ) -> None:
        """Execute either trigger under one snapshot and one finalization path."""
        store, recovery, settings = runtime.store, runtime.recovery, runtime.settings
        snapshot = store.begin_background(self.id) if background else store.begin(self.id, owner)
        if snapshot is None:
            return
        output = RunOutput()
        replay: ReplayTurn | None = None
        try:
            attachments = store.attachments(self.id)
            turn.admitting = True
            if background:
                if recovery.history_log is not None and not await recovery.history_log.write(
                    "start_recovery_turn",
                    turn.id,
                    self.id,
                    None,
                    question,
                    {"kind": "background", "model": settings.provider_model, "attachment_count": len(attachments)},
                ):
                    output.error_code = "internal_error"
                    await self._finish_background(
                        runtime,
                        turn,
                        snapshot,
                        output,
                        (
                            "error",
                            {
                                "message": "AI message recovery is unavailable, so the optimizer result was not reviewed."
                            },
                        ),
                    )
                    return
            else:
                request_logger.info(
                    "AI request started session_id=%s question_chars=%s question=%s files=%s",
                    self.id,
                    len(question),
                    json.dumps(_question_log_preview(question), ensure_ascii=False),
                    len(attachments),
                )
                if not await recovery.save_session(self.id):
                    raise RuntimeError("AI message recovery is temporarily unavailable.")
                replay = await recovery.turn_journal.start(
                    self.id,
                    turn.id,
                    message_id or turn.id,
                    question,
                    {
                        "model": settings.provider_model,
                        "auth_credential_id": credential_id,
                        "attachment_count": len(attachments),
                    },
                )
                if accepted is not None:
                    accepted(replay)
                turn.ready.set_result(True)
            turn.admitting = False
            events = self._generate(runtime, turn, snapshot, question, attachments, artifact, output, background)
            if background:
                await self._deliver_background(runtime, turn, snapshot, events, output)
            else:
                await self._deliver_foreground(runtime, turn, events, output, replay)
        finally:
            turn.admitting = False
            store.abort(self.id, snapshot)
            self.agent.reset()

    async def _generate(self, runtime, turn, snapshot, question, attachments, artifact, output, background):
        settings = runtime.settings
        history, schedule_yaml = snapshot.transcript, snapshot.schedule_yaml
        try:
            if turn.cancelled or (
                not background and await runtime.recovery.turn_journal.was_stopped(self.id, turn.message_id or turn.id)
            ):
                raise asyncio.CancelledError
            if background:
                yield "turn_start", {"message_id": turn.id, "trigger": "optimizer"}
            else:
                artifact = await runtime.session_optimizer.latest_result_artifact(self.id)
            selected = project_history(history, settings.max_history_chars)
            retained = selected.messages
            dropped = snapshot.dropped_history_messages + selected.dropped_messages
            messages = build_provider_messages(
                selected,
                schedule_yaml,
                question,
                attachments,
                system_prompt=SANDBOX_SYSTEM_PROMPT,
                pending_proposal=bool(snapshot.proposal_yaml),
                optimizer_result_available=artifact is not None,
                max_history_chars=settings.max_history_chars,
                max_download_bytes=settings.max_download_bytes,
            )
            context_chars = selected.used_chars
            if background:
                yield "context_usage", context_usage(context_chars, settings)
                if dropped:
                    yield "history_trimmed", {"dropped": dropped}
                yield "model_input", model_input(messages, len(retained), dropped, "optimizer")
            else:
                yield "model_input", model_input(messages, len(retained), dropped, "question")
                yield "context_usage", context_usage(context_chars, settings)
                if dropped:
                    yield "history_trimmed", {"dropped": dropped}
            async with runtime.concurrency_limit:
                agent_events = run_workspace(
                    runtime.provider,
                    runtime.sandbox_factory,
                    schedule_yaml,
                    messages,
                    WorkspaceLimits.from_settings(settings),
                    take_steering=None if background else lambda close: runtime.store.take_steering(self.id, close),
                    pending_proposal_yaml=snapshot.proposal_yaml,
                    pending_proposal_diff=snapshot.proposal_diff,
                    execute_optimizer=lambda current_yaml, arguments: execute_optimizer_tool(
                        runtime.session_optimizer, self.id, current_yaml, arguments
                    ),
                    attachments=attachments,
                    optimizer_result=artifact.content if artifact is not None else None,
                    optimizer_context=artifact.schedule_context if artifact is not None else None,
                    agent=self.agent,
                )
                async with aclosing(agent_events):
                    async for event in agent_events:
                        projected = output.apply(event)
                        if isinstance(event, TokenUsage):
                            projected = (
                                "context_usage",
                                context_usage(context_chars, settings, event, runtime.provider),
                            )
                        if projected is not None:
                            yield projected
            completion = runtime.store.finish(
                self.id,
                question,
                output.text,
                (output.proposal.text, output.proposal.diff) if output.proposal is not None else None,
                snapshot=snapshot,
                turn_messages=[UserMessage(question), *self.agent.state.messages],
            )
            output.completed = True
            turn.finishing = True
            output.saved_outcome = (
                ("done", {"message_id": turn.id}) if completion.turn_saved else ("stale", {"message": STALE_TURN_ERROR})
            )
            if not completion.turn_saved:
                yield output.saved_outcome
                return
            if completion.history_trimmed_count and completion.history_trimmed_count != dropped:
                yield "history_trimmed", {"dropped": completion.history_trimmed_count}
            if completion.proposal_saved:
                yield "proposal", {"diff": output.proposal.diff}
            if output.download is not None:
                if runtime.store.save_download(self.id, turn.id, output.download):
                    yield "download", {"download_id": turn.id}
                else:
                    yield (
                        "warning",
                        {
                            "message": "The generated ZIP could not be retained because the service memory limit was reached."
                        },
                    )
            yield (
                "context_usage",
                context_usage(completion.context_used_chars, settings, output.last_call, runtime.provider),
            )
            yield output.saved_outcome
        except asyncio.CancelledError:
            yield output.saved_outcome or ("stopped", {"message_id": turn.id})
        except ProviderError as exc:
            output.error_code = "provider_error"
            yield "error", {"message": exc.user_message or PROVIDER_ERROR}
        except SandboxDownloadError as exc:
            output.error_code = "download_error"
            yield "error", {"message": str(exc)}
        except SandboxCommandTimeoutError:
            output.error_code = "sandbox_command_timeout"
            yield "error", {"message": SANDBOX_COMMAND_TIMEOUT_ERROR}
        except SandboxTurnTimeoutError:
            output.error_code = "sandbox_timeout"
            yield "error", {"message": SANDBOX_TURN_TIMEOUT_ERROR}
        except SandboxCandidateError as exc:
            output.error_code = "candidate_validation"
            logger.warning("AI candidate validation failed: %s", exc)
            yield (
                "error",
                {"message": CANDIDATE_VALIDATION_ERROR + (f"\n\n{exc.user_message}" if exc.user_message else "")},
            )
        except SandboxError:
            output.error_code = "sandbox_error"
            logger.exception("AI sandbox turn failed session_id=%s", self.id)
            yield (
                "error",
                {
                    "message": "The temporary AI sandbox failed while reviewing optimizer results."
                    if background
                    else "The temporary AI sandbox failed. Please try again."
                },
            )
        except Exception:
            output.error_code = "internal_error"
            logger.exception("Unexpected AI stream failure session_id=%s", self.id)
            yield (
                "error",
                {
                    "message": "The AI could not review the optimizer result."
                    if background
                    else "The AI response failed unexpectedly."
                },
            )
        finally:
            if not output.completed:
                if self.agent.state.messages:
                    reason = "error" if output.error_code is not None else "aborted"
                    runtime.store.finish(
                        self.id,
                        question,
                        "",
                        snapshot=snapshot,
                        turn_messages=interrupted_entries([UserMessage(question), *self.agent.state.messages], reason),
                    )
                runtime.store.abort(self.id, snapshot)

    async def _deliver_background(self, runtime, turn, snapshot, events, output):
        terminal = None
        try:
            async with aclosing(events):
                async for kind, data in events:
                    if kind in TERMINAL_EVENTS:
                        terminal = kind, data
                    elif not turn.retired:
                        await runtime.recovery.event_broker.emit(self.id, kind, {**data, "turn_id": turn.id})
        except asyncio.CancelledError:
            terminal = output.saved_outcome or ("stopped", {"message_id": turn.id})
        except Exception:
            output.error_code = "internal_error"
            logger.exception("Background AI recovery failed session_id=%s", self.id)
            terminal = ("error", {"message": "The AI could not review the optimizer result."})
        finally:
            if terminal is not None:
                await self._finish_background(runtime, turn, snapshot, output, terminal)
        if terminal is not None and terminal[0] == "stopped":
            raise asyncio.CancelledError

    async def _finish_background(self, runtime, turn, snapshot, output, terminal):
        turn.finishing = True
        if turn.retired:
            return
        if not output.completed:
            runtime.store.abort(self.id, snapshot)
        kind, data = terminal
        await runtime.recovery.event_broker.emit(self.id, kind, {**data, "turn_id": turn.id}, metadata=output.metadata)

    async def _deliver_foreground(self, runtime, turn, events, output, replay):
        queue = asyncio.Queue(maxsize=64)
        terminal = None

        async def collect():
            try:
                async with aclosing(events):
                    async for event in events:
                        await queue.put(event)
            except asyncio.CancelledError:
                await queue.put(output.saved_outcome or ("stopped", {"message_id": turn.id}))
            finally:
                await queue.put(None)

        collector = asyncio.create_task(collect(), name=f"ai-output-{turn.id}")
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
                    if event["type"] in TERMINAL_EVENTS:
                        terminal = event["type"], event["data"]
                    else:
                        await runtime.recovery.turn_journal.publish(replay, event["type"], event["data"])
        except asyncio.CancelledError:
            terminal = output.saved_outcome or terminal
            if terminal is None and not runtime.recovery.shutting_down:
                terminal = ("stopped", {"message_id": turn.id})
        except Exception:
            logger.exception("AI turn recovery failed session_id=%s", self.id)
            terminal = (
                "error",
                {"message": "AI message recovery is temporarily unavailable. Reconnect to check the saved response."},
            )
        finally:
            turn.finishing = True
            if not collector.done():
                collector.cancel()
            # Free a producer blocked by the queue before joining its cleanup.
            while not queue.empty():
                event = queue.get_nowait()
                if terminal is None and event and event[0] in TERMINAL_EVENTS:
                    terminal = event
            await asyncio.gather(collector, return_exceptions=True)
            if self.id in runtime.store._sessions:
                if runtime.recovery.shutting_down and terminal is not None and terminal[0] == "stopped":
                    terminal = None
                if terminal is not None:
                    async with runtime.recovery.state_write_lock(self.id):
                        if self.id in runtime.store._sessions:
                            saved = await runtime.recovery.turn_journal.finish(
                                replay, *terminal, state=runtime.store.recovery_state(self.id), metadata=output.metadata
                            )
                            runtime.recovery.record_save(self.id, saved)
                else:
                    await runtime.recovery.save_session(self.id)


@dataclass(frozen=True)
class SessionRuntime:
    """Shared execution dependencies, separate from session-owned state."""

    settings: AiSettings
    store: SessionStore
    turns: SessionTurns
    recovery: SessionRecovery
    provider: ToolCapableChatProvider
    sandbox_factory: SandboxFactory
    session_optimizer: SessionOptimizer
    concurrency_limit: asyncio.Semaphore


@dataclass
class RunOutput:
    """Collect one transaction and project model events onto the existing API."""

    assistant_parts: list[str] = field(default_factory=list)
    proposal: AgentProposal | None = None
    download: bytes | None = None
    usage: TokenUsage | None = None
    last_call: TokenUsage | None = None
    completed: bool = False
    saved_outcome: tuple[str, dict] | None = None
    error_code: str | None = None

    @property
    def text(self) -> str:
        return "".join(self.assistant_parts)

    @property
    def metadata(self) -> dict:
        return {"error_code": self.error_code, "usage": asdict(self.usage) if self.usage else None}

    def apply(self, event):
        if isinstance(event, AgentText):
            self.assistant_parts.append(event.text)
            return "delta", {"text": event.text}
        if isinstance(event, AgentReasoning):
            return "reasoning", {"text": event.text}
        if isinstance(event, TokenUsage):
            self.usage = event if self.usage is None else self.usage + event
            self.last_call = event
        elif isinstance(event, AgentToolStart):
            return "tool_start", {"name": event.name, "arguments": event.arguments}
        elif isinstance(event, AgentToolUse):
            return "tool", {"name": event.name, "arguments": event.arguments, "result": event.result, "ok": event.ok}
        elif isinstance(event, AgentSteering):
            return "steering", {"message_id": event.message_id, "message": event.text}
        elif isinstance(event, AgentScheduleChange):
            return "schedule_change", {"schedule_yaml": event.schedule_yaml}
        elif isinstance(event, AgentDownload):
            self.download = event.content
        elif isinstance(event, AgentProposal):
            self.proposal = event
        return None
