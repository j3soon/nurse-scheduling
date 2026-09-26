"""Application session state and transactional agent run finalization."""

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

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException

from .agent import Agent
from .agent_types import (
    AgentEvent,
    AgentProposal,
    AgentSteering,
    MessageReasoningDelta,
    MessageTextDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from .config import AiSettings
from .context import build_provider_messages, recent_history
from .history import ChatHistory
from .lifecycle import AgentRun, RunSnapshot
from .optimizer import OptimizerArtifact, SessionOptimizer
from .provider import ChatMessage, ProviderError, TokenUsage, ToolCapableChatProvider
from .sandbox import SandboxError, SandboxFactory
from .workspace import (
    AgentScheduleChange,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxRunTimeoutError,
    WorkspaceLimits,
)
from .workspace_tools import run_workspace

CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent turn were "
    "discarded. The canonical schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_TURN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_TURN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
logger = logging.getLogger("nurse_scheduling.ai")


class RunCompletion(Protocol):
    """Result fields used by run finalization."""

    run_saved: bool
    proposal_saved: bool
    history_trimmed_count: int


class SessionPersistence(Protocol):
    """Session operations needed by a foreground or background run."""

    def begin(self, session_id: str, owner_token: str | None) -> RunSnapshot: ...

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]: ...

    def begin_background(self, session_id: str) -> RunSnapshot | None: ...

    def finish(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        proposal: tuple[str, str] | None = None,
        *,
        snapshot: RunSnapshot,
        run_messages: Sequence[ChatMessage] = (),
    ) -> RunCompletion: ...

    def abort(self, session_id: str, snapshot: RunSnapshot) -> None: ...


@dataclass(frozen=True)
class SessionRuntime:
    """Shared service dependencies for foreground and optimizer-triggered runs."""

    settings: AiSettings
    store: SessionPersistence
    concurrency_limit: asyncio.Semaphore
    history_log: ChatHistory | None
    provider: ToolCapableChatProvider
    sandbox_factory: SandboxFactory
    session_optimizer: SessionOptimizer


@dataclass
class RunOutput:
    """Collect transactional history and project agent events onto the existing SSE contract."""

    messages: list[ChatMessage]
    assistant_parts: list[str] = field(default_factory=list)
    assistant_segment: list[str] = field(default_factory=list)
    proposal: AgentProposal | None = None
    usage: TokenUsage | None = None

    @property
    def text(self) -> str:
        return "".join(self.assistant_parts)

    def finish_messages(self) -> list[ChatMessage]:
        return [*self.messages, ChatMessage(role="assistant", content="".join(self.assistant_segment))]

    def consume(self, event: AgentEvent | AgentScheduleChange) -> tuple[str, dict[str, object]] | None:
        if isinstance(event, MessageTextDelta):
            self.assistant_parts.append(event.text)
            self.assistant_segment.append(event.text)
            return "delta", {"text": event.text}
        if isinstance(event, MessageReasoningDelta):
            return "reasoning", {"text": event.text}
        if isinstance(event, TokenUsage):
            self.usage = event if self.usage is None else self.usage + event
        elif isinstance(event, ToolExecutionStart):
            return "tool_start", {"name": event.name, "arguments": event.arguments}
        elif isinstance(event, ToolExecutionEnd):
            return "tool", {"name": event.name, "arguments": event.arguments, "result": event.result, "ok": event.ok}
        elif isinstance(event, AgentSteering):
            if self.assistant_segment:
                self.messages.append(ChatMessage(role="assistant", content="".join(self.assistant_segment)))
            self.messages.append(ChatMessage(role="user", content=event.text))
            self.assistant_segment.clear()
            return "steering", {"message_id": event.message_id, "message": event.text}
        elif isinstance(event, AgentScheduleChange):
            return "schedule_change", {"schedule_yaml": event.schedule_yaml}
        elif isinstance(event, AgentProposal):
            self.proposal = event
        return None


@dataclass
class AgentSession:
    """Process-local conversation state owned by one browser cookie."""

    id: str
    owner_token: str
    expires_at: float
    schedule_yaml: str
    revision: str
    history: list[ChatMessage] = field(default_factory=list)
    dropped_history_messages: int = 0
    version: int = 0
    snapshot: RunSnapshot | None = None
    agent: Agent = field(default_factory=Agent)
    proposal_yaml: str = ""
    proposal_diff: str = ""

    @property
    def active(self) -> bool:
        return self.snapshot is not None

    async def run(
        self,
        run: AgentRun,
        question: str,
        *,
        runtime: SessionRuntime,
        emit: Callable[[str, dict[str, object]], Awaitable[None]],
        background: bool = False,
        owner: str | None = None,
        credential_id: str | None = None,
        attachments: Sequence[SandboxAttachment] = (),
        artifact: OptimizerArtifact | None = None,
    ) -> None:
        """Own every run phase and finalize once, regardless of trigger or transport."""
        session_id = self.id
        settings, store = runtime.settings, runtime.store
        concurrency_limit, history_log = runtime.concurrency_limit, runtime.history_log
        provider, sandbox_factory = runtime.provider, runtime.sandbox_factory
        session_optimizer = runtime.session_optimizer
        snapshot = store.begin_background(session_id) if background else store.begin(session_id, owner)
        if snapshot is None:
            return
        self.agent.active_run = run
        history, schedule_yaml = snapshot.history, snapshot.schedule_yaml
        proposal_yaml, proposal_diff = snapshot.proposal_yaml, snapshot.proposal_diff
        history_question = question
        if attachments:
            filenames = json.dumps([attachment.filename for attachment in attachments], ensure_ascii=False)
            history_question += f"\n[Files were attached: {filenames}.]"
        output = RunOutput([ChatMessage(role="user", content=history_question)])
        completed = False
        logged = False
        outcome = "cancelled"
        error_code = None
        publish = emit
        terminal_event: tuple[str, dict[str, object]] | None = None

        async def emit(event_type: str, data: dict[str, object]) -> None:
            nonlocal terminal_event
            # Every replayable fragment identifies its turn, even after turn_start expires.
            data = {**data, "turn_id": run.id} if background else data
            if event_type in {"done", "stopped", "stale", "error"}:
                terminal_event = event_type, data
            else:
                await publish(event_type, data)

        async def write_history(operation: str, *args) -> bool:
            # asyncio cancellation and ASGI cancel scopes both wait for the history write.
            task = asyncio.create_task(history_log.write(operation, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise

        try:
            if background:
                await emit("turn_start", {"message_id": run.id, "trigger": "optimizer"})
            if history_log is not None:
                logged = True
                logged = await write_history(
                    "start_turn",
                    run.id,
                    session_id,
                    credential_id,
                    question,
                    settings.provider_model,
                    len(attachments),
                )
                if not logged:
                    raise HTTPException(status_code=503, detail="AI chat history is temporarily unavailable.")
            run.ready.set_result(True)
            if not background:
                artifact = await session_optimizer.latest_result_artifact(session_id)
                await run.streaming.wait()
            retained_history = recent_history(history, settings.max_history_chars)
            dropped_history = snapshot.previously_dropped + len(history) - len(retained_history)
            if dropped_history:
                await emit("history_trimmed", {"dropped": dropped_history})
            messages = build_provider_messages(
                retained_history,
                schedule_yaml,
                question,
                attachments,
                pending_proposal=bool(proposal_yaml),
                optimizer_result_available=artifact is not None,
                max_history_chars=settings.max_history_chars,
            )
            async with concurrency_limit:
                agent_events = run_workspace(
                    provider,
                    sandbox_factory,
                    schedule_yaml,
                    messages,
                    WorkspaceLimits.from_settings(settings),
                    take_steering=None if background else lambda close: store.take_steering(session_id, close),
                    pending_proposal_yaml=proposal_yaml,
                    pending_proposal_diff=proposal_diff,
                    execute_optimizer=lambda current_yaml, arguments: session_optimizer.execute(
                        session_id, current_yaml, arguments
                    ),
                    attachments=attachments,
                    optimizer_result=artifact.content if artifact is not None else None,
                    agent=self.agent,
                )
                async with aclosing(agent_events):
                    async for event in agent_events:
                        wire_event = output.consume(event)
                        if wire_event is not None:
                            await emit(*wire_event)
            completion = store.finish(
                session_id,
                history_question,
                output.text,
                (output.proposal.text, output.proposal.diff) if output.proposal is not None else None,
                snapshot=snapshot,
                run_messages=output.finish_messages(),
            )
            completed = True
            outcome = "completed" if completion.run_saved else "stale"
            history_saved = None
            if logged:
                # The history result is part of foreground done. Do not write it again in finally.
                logged = False
                history_saved = await write_history("finish_turn", run.id, output.text, outcome, None, output.usage)
            if not completion.run_saved:
                await emit("stale", {"message": STALE_TURN_ERROR})
                return
            if completion.history_trimmed_count and completion.history_trimmed_count != dropped_history:
                await emit("history_trimmed", {"dropped": completion.history_trimmed_count})
            if completion.proposal_saved and output.proposal is not None:
                await emit("proposal", {"diff": output.proposal.diff})
            done = {"message_id": run.id}
            if history_saved is not None and not background:
                done["history_saved"] = history_saved
            await emit("done", done)
        except asyncio.CancelledError:
            if background:
                await emit("stopped", {"message_id": run.id})
            raise
        except HTTPException:
            if not background:
                raise
            outcome, error_code = "failed", "history_unavailable"
            await emit(
                "error", {"message": "AI chat history is unavailable, so the optimizer result was not reviewed."}
            )
        except (ProviderError, SandboxRunTimeoutError, SandboxCandidateError, SandboxError) as exc:
            outcome = "failed"
            if isinstance(exc, ProviderError):
                error_code, message = "provider_error", PROVIDER_ERROR
            elif isinstance(exc, SandboxRunTimeoutError):
                error_code, message = "sandbox_timeout", SANDBOX_TURN_TIMEOUT_ERROR
            elif isinstance(exc, SandboxCandidateError):
                error_code, message = "candidate_validation", CANDIDATE_VALIDATION_ERROR
            else:
                error_code, message = "sandbox_error", "The temporary AI sandbox failed. Please try again."
                logger.exception("AI sandbox turn failed session_id=%s", session_id)
            await emit("error", {"message": message})
        except Exception:
            outcome, error_code = "failed", "internal_error"
            logger.exception("Unexpected AI turn failure session_id=%s", session_id)
            await emit("error", {"message": "The AI response failed unexpectedly."})
        finally:
            run.finishing = True
            try:
                if not completed:
                    store.abort(session_id, snapshot)
                if logged:
                    await write_history("finish_turn", run.id, output.text, outcome, error_code, output.usage)
                if terminal_event is not None:
                    await publish(*terminal_event)
            finally:
                self.agent.active_run = None
