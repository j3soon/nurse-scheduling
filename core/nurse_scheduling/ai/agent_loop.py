"""The model loop for executable agent tools."""

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
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing, asynccontextmanager
from datetime import datetime

from .agent_types import (
    AgentMessageEnd,
    AgentReasoning,
    AgentSteering,
    AgentText,
    AgentTool,
    AgentToolBatchMetrics,
    AgentToolOutcome,
    AgentToolStart,
    AgentToolUse,
    SteeringSource,
    ToolBatchObserver,
    ToolBatchScope,
    ToolExecutor,
)
from .context import prepare_provider_request
from .provider import (
    ChatMessage,
    ReasoningDelta,
    ResponseEnd,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallRequest,
    ToolCapableChatProvider,
)
from .transcript import AgentMessage, AssistantMessage, ToolResultMessage, UserMessage

logger = logging.getLogger("nurse_scheduling.ai.agent")

TRUNCATED_TOOL_CALL_RESULT = (
    "The response reached the output token limit before this tool call was complete, so it was not run. "
    "Issue it again with shorter arguments, or split the work into smaller steps."
)


@asynccontextmanager
async def _unbatched_activity() -> AsyncIterator[None]:
    yield


async def agent_loop(
    provider: ToolCapableChatProvider,
    messages: Sequence[ChatMessage],
    tools: Sequence[AgentTool],
    activity_batch: ToolBatchScope | None = None,
    observe_tool_batch: ToolBatchObserver | None = None,
    take_steering: SteeringSource | None = None,
    max_tool_rounds: int | None = None,
    max_tool_calls: int | None = None,
    run_messages: list[AgentMessage] | None = None,
    request_clock: Callable[[], datetime] | None = None,
) -> AsyncIterator[AgentText | AgentReasoning | AgentToolStart | AgentToolUse]:
    """Run the model/tool loop shared by agent capability layers."""
    registered = {tool.name: tool for tool in tools}

    async def execute(name: str, arguments: str) -> AgentToolOutcome:
        tool = registered.get(name)
        if tool is None:
            return AgentToolOutcome(f"Unknown tool `{name}`. Available tools: {', '.join(registered)}.", False)
        return await tool.execute(arguments)

    conversation = [] if run_messages is None else run_messages
    tool_rounds = 0
    tool_calls = 0
    final_answer_only = False
    while True:
        # Every follow-up request must include steering accepted during the last response,
        # including tool refusals that continue without an execution batch.
        if conversation and take_steering is not None:
            for message_id, text in take_steering(False):
                conversation.append(UserMessage(text))
                yield AgentSteering(message_id, text)
        answer, reasoning, calls = [], [], ()
        finish_reason = None
        provider_events = provider.stream_events(
            prepare_provider_request(messages, conversation, now=request_clock() if request_clock else None),
            [] if final_answer_only else [tool.definition for tool in tools],
        )
        try:
            async with aclosing(provider_events):
                async for event in provider_events:
                    if isinstance(event, TextDelta):
                        answer.append(event.text)
                        yield AgentText(event.text)
                    elif isinstance(event, ReasoningDelta):
                        reasoning.append(event.text)
                        yield AgentReasoning(event.text)
                    elif isinstance(event, TokenUsage):
                        yield event
                    elif isinstance(event, ToolCallRequest):
                        calls = event.calls
                    elif isinstance(event, ResponseEnd):
                        finish_reason = event.finish_reason
        except BaseException as exc:
            reason = "aborted" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else "error"
            conversation.append(AssistantMessage("".join(answer), reason, "".join(reasoning), calls))
            raise
        stop_reason = "length" if finish_reason == "length" else "tool_use" if calls else "stop"
        response = AssistantMessage("".join(answer), stop_reason, "".join(reasoning), calls)
        conversation.append(response)
        yield AgentMessageEnd(response)
        if not calls:
            steering = tuple(take_steering(True)) if take_steering is not None else ()
            if not steering:
                break
            for message_id, text in steering:
                conversation.append(UserMessage(text))
                yield AgentSteering(message_id, text)
            continue

        exceeds_rounds = max_tool_rounds is not None and tool_rounds >= max_tool_rounds
        exceeds_calls = max_tool_calls is not None and tool_calls + len(calls) > max_tool_calls
        if final_answer_only or exceeds_rounds or exceeds_calls:
            if final_answer_only:
                break
            for call in calls:
                outcome = AgentToolOutcome(
                    "The trusted tool budget is exhausted. Finish with the verified information already available.",
                    False,
                )
                yield AgentToolStart(call.name, call.arguments, call.id)
                yield _record_tool_result(conversation, call, outcome)
            final_answer_only = True
            continue

        tool_rounds += 1
        tool_calls += len(calls)
        if finish_reason == "length":
            # Even valid JSON can describe a different operation when cut short.
            for call in calls:
                yield AgentToolStart(call.name, call.arguments, call.id)
                yield _record_tool_result(conversation, call, AgentToolOutcome(TRUNCATED_TOOL_CALL_RESULT, False))
            final_answer_only = (max_tool_rounds is not None and tool_rounds >= max_tool_rounds) or (
                max_tool_calls is not None and tool_calls >= max_tool_calls
            )
            continue
        batch_scope = activity_batch or _unbatched_activity
        async with batch_scope():
            terminal = False
            completed_calls = 0
            parallel = len(calls) > 1 and all(
                call.name in registered and registered[call.name].read_only for call in calls
            )
            if parallel:
                for call in calls:
                    yield AgentToolStart(call.name, call.arguments, call.id)
                started = time.perf_counter()
                outcomes = await _execute_parallel_tool_calls(calls, execute)
                execution_seconds = time.perf_counter() - started
                completed = zip(calls, outcomes, strict=True)
                for call, outcome in completed:
                    yield _record_tool_result(conversation, call, outcome)
                    completed_calls += 1
                    terminal = terminal or outcome.terminal
            else:
                execution_seconds = 0.0
                for call in calls:
                    yield AgentToolStart(call.name, call.arguments, call.id)
                    started = time.perf_counter()
                    outcome = await execute(call.name, call.arguments)
                    execution_seconds += time.perf_counter() - started
                    yield _record_tool_result(conversation, call, outcome)
                    completed_calls += 1
                    terminal = terminal or outcome.terminal
                    if terminal:
                        break
            if observe_tool_batch is not None:
                observe_tool_batch(AgentToolBatchMetrics(completed_calls, parallel, execution_seconds))
        if terminal:
            return


def _record_tool_result(conversation: list[AgentMessage], call: ToolCall, outcome: AgentToolOutcome) -> AgentToolUse:
    """Record the provider result once before publishing its completion."""
    _log_tool_outcome(call.name, outcome)
    conversation.append(ToolResultMessage(call.id, call.name, outcome.text, outcome.ok, outcome.image))
    return AgentToolUse(call.name, call.arguments, outcome.text, outcome.ok, call.id, outcome.details)


async def _execute_parallel_tool_calls(
    calls: Sequence[ToolCall],
    execute: ToolExecutor,
) -> list[AgentToolOutcome]:
    tasks = [asyncio.create_task(execute(call.name, call.arguments)) for call in calls]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def _log_tool_outcome(name: str, outcome: AgentToolOutcome) -> None:
    logger.info(
        "agent tool call name=%s ok=%s result_chars=%s image_bytes=%s",
        name,
        outcome.ok,
        len(outcome.text),
        len(outcome.image.data) if outcome.image is not None else 0,
    )
