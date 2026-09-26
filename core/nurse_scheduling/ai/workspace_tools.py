"""Workspace tool bindings and run-scoped sandbox integration."""

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
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing, asynccontextmanager
from functools import partial

from .agent import Agent
from .agent_types import AgentEvent, AgentProposal, AgentTool, AgentToolBatchMetrics, AgentToolResult, ToolExecutionEnd
from .candidate import review_schedule_candidate
from .context import prepare_provider_request
from .optimizer import OPTIMIZER_TOOL, optimizer_tool_definition
from .pi.read import READ_TOOL
from .provider import ChatMessage, ToolCapableChatProvider
from .sandbox import SandboxFactory, SandboxFileNotFoundError
from .sandbox_tools import SandboxPiTools
from .transcript import ToolCall
from .workspace import (
    WORKSPACE_SCHEDULE,
    AgentScheduleChange,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxRunMetrics,
    SandboxRunTimeoutError,
    SandboxWorkspace,
    WorkspaceLimits,
    _read_candidate,
    _ScheduleCandidateTracker,
    sandbox_workspace,
)

logger = logging.getLogger("nurse_scheduling.ai.workspace_tools")


class WorkspaceTools:
    """Bind workspace validation and optimizer dispatch to executable agent tools."""

    def __init__(
        self,
        sandbox: SandboxWorkspace,
        schedule_yaml: str,
        limits: WorkspaceLimits,
        execute_optimizer: Callable[[str, str], Awaitable[AgentToolResult]] | None,
    ) -> None:
        self.sandbox = sandbox
        self.schedule_yaml = schedule_yaml
        self.limits = limits
        self.execute_optimizer = execute_optimizer
        self.sandbox_tools = SandboxPiTools(sandbox, limits.bash_command_timeout_seconds)
        self._sandbox_tool_names = {definition["function"]["name"] for definition in self.sandbox_tools.definitions}
        self.candidate_tracker = _ScheduleCandidateTracker(sandbox, schedule_yaml, limits.max_schedule_bytes)
        definitions = list(self.sandbox_tools.definitions)
        if execute_optimizer is not None:
            definitions.append(optimizer_tool_definition(limits.optimizer_default_timeout_seconds))
        self.tools = [
            AgentTool(
                definition,
                partial(self._execute, definition["function"]["name"]),
                definition["function"]["name"] == READ_TOOL,
            )
            for definition in definitions
        ]

    def needs_workspace(self, name: str, arguments: str) -> bool:
        if name != OPTIMIZER_TOOL:
            return name in self._sandbox_tool_names
        if self.execute_optimizer is None:
            return False
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, dict) and parsed.get("action", "start") == "start"

    async def _execute(self, name: str, arguments: str) -> AgentToolResult:
        if name == OPTIMIZER_TOOL and self.execute_optimizer is not None:
            if not self.needs_workspace(name, arguments):
                return await self.execute_optimizer("", arguments)
            try:
                current_schedule = (await self.sandbox.read_file(WORKSPACE_SCHEDULE)).decode("utf-8")
            except (SandboxFileNotFoundError, UnicodeDecodeError):
                return AgentToolResult("The current working schedule is unavailable or invalid.", False)
            review = review_schedule_candidate(self.schedule_yaml, current_schedule, self.limits.max_schedule_bytes)
            if not review.outcome.ok:
                return AgentToolResult(f"Trusted schedule check before optimizer:\n{review.outcome.text}", False)
            return await self.execute_optimizer(current_schedule, arguments)
        outcome = await self.sandbox_tools.execute(name, arguments)
        if name == READ_TOOL:
            return outcome
        candidate_status = await self.candidate_tracker.review_if_changed()
        if candidate_status is None:
            return outcome
        validation, schedule_change = candidate_status
        return AgentToolResult(
            f"{outcome.text}\n\n{validation.text}",
            outcome.ok and validation.ok,
            details={"schedule_yaml": schedule_change} if schedule_change is not None else None,
        )


async def run_workspace(
    provider: ToolCapableChatProvider,
    factory: SandboxFactory,
    schedule_yaml: str,
    messages: Sequence[ChatMessage],
    limits: WorkspaceLimits,
    metrics: SandboxRunMetrics | None = None,
    observe_tool_batch: Callable[[AgentToolBatchMetrics], None] | None = None,
    take_steering: Callable[[bool], Sequence[tuple[str, str]]] | None = None,
    pending_proposal_yaml: str = "",
    pending_proposal_diff: str = "",
    execute_optimizer: Callable[[str, str], Awaitable[AgentToolResult]] | None = None,
    attachments: Sequence[SandboxAttachment] = (),
    optimizer_result: bytes | None = None,
    agent: Agent | None = None,
) -> AsyncIterator[AgentEvent | AgentScheduleChange]:
    """Hydrate, run, read, validate, and destroy one fresh workspace run."""
    agent = agent or Agent()
    metrics = metrics or SandboxRunMetrics()
    try:
        async with asyncio.timeout(limits.run_timeout_seconds):
            async with sandbox_workspace(
                factory,
                limits.cleanup_timeout_seconds,
                metrics,
                schedule_yaml,
                pending_proposal_yaml,
                pending_proposal_diff,
                attachments,
                optimizer_result,
            ) as sandbox:
                toolset = WorkspaceTools(sandbox, schedule_yaml, limits, execute_optimizer)

                @asynccontextmanager
                async def tool_batch(calls: Sequence[ToolCall]) -> AsyncIterator[None]:
                    if any(toolset.needs_workspace(call.name, call.arguments) for call in calls):
                        async with sandbox.activity_batch():
                            yield
                    else:
                        yield

                events = agent.prompt(
                    provider,
                    messages,
                    toolset.tools,
                    activity_batch=tool_batch,
                    observe_tool_batch=observe_tool_batch,
                    take_steering=take_steering,
                    max_tool_rounds=limits.max_tool_rounds,
                    max_tool_calls=limits.max_tool_calls,
                    prepare_request=prepare_provider_request,
                )
                async with aclosing(events):
                    async for event in events:
                        yield event
                        if isinstance(event, ToolExecutionEnd) and event.details is not None:
                            yield AgentScheduleChange(event.details["schedule_yaml"])

                if not sandbox.started:
                    return
                candidate = await _read_candidate(sandbox, limits.max_schedule_bytes)
                review = review_schedule_candidate(schedule_yaml, candidate, limits.max_schedule_bytes)
                logger.info(
                    "sandbox candidate validated sandbox_id=%s valid=%s proposal=%s",
                    sandbox.sandbox_id,
                    review.outcome.ok,
                    review.proposal is not None,
                )
                if not review.outcome.ok:
                    raise SandboxCandidateError("The sandbox candidate failed trusted schedule validation.")
                if review.proposal is not None:
                    yield AgentProposal(review.proposal.text, review.proposal.diff.render())
    except TimeoutError as exc:
        raise SandboxRunTimeoutError(
            f"The sandbox agent run exceeded its {limits.run_timeout_seconds:g}-second limit."
        ) from exc
    finally:
        logger.info(
            "sandbox timing lifetime_seconds=%.3f provisioning_seconds=%.3f execution_seconds=%.3f "
            "pause_transition_seconds=%.3f warm_waiting_seconds=%.3f suspended_seconds=%.3f "
            "resume_wait_seconds=%.3f teardown_seconds=%.3f pause_count=%s pause_cancel_count=%s resume_count=%s",
            metrics.lifetime_seconds,
            metrics.provisioning_seconds,
            metrics.execution_seconds,
            metrics.pause_transition_seconds,
            metrics.warm_waiting_seconds,
            metrics.suspended_seconds,
            metrics.resume_wait_seconds,
            metrics.teardown_seconds,
            metrics.pause_count,
            metrics.pause_cancel_count,
            metrics.resume_count,
        )
