"""The provider and tool loop behind one assistant answer."""

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
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from .agent_types import (
    AgentEvent,
    AgentSteering,
    AgentTool,
    AgentToolBatchMetrics,
    AgentToolResult,
    MessageEnd,
    MessageReasoningDelta,
    MessageTextDelta,
    RequestPreparer,
    SteeringSource,
    ToolBatchObserver,
    ToolBatchScope,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from .context import prepare_provider_request
from .provider import (
    ChatMessage,
    ReasoningDelta,
    ResponseEnd,
    TextDelta,
    TokenUsage,
    ToolCallRequest,
    ToolCapableChatProvider,
)
from .transcript import AgentMessage, AssistantMessage, ToolCall, ToolResultMessage, UserMessage

logger = logging.getLogger("nurse_scheduling.ai.agent")

TRUNCATED_TOOL_CALL_RESULT = (
    "The response reached the output token limit before this tool call was complete, so it was not run. "
    "Issue it again with shorter arguments, or split the work into smaller steps."
)


@asynccontextmanager
async def _unbatched_activity(_calls: Sequence[ToolCall]) -> AsyncIterator[None]:
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
    prepare_request: RequestPreparer = prepare_provider_request,
    run_messages: list[AgentMessage] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run the model/tool loop shared by agent capability layers.

    `run_messages` is the canonical in-run record. Each provider request is a
    projection of it after the already bounded system and prior-run context.
    """
    by_name = {tool.name: tool for tool in tools}
    definitions = [tool.definition for tool in tools]

    async def execute(name: str, arguments: str) -> AgentToolResult:
        tool = by_name.get(name)
        if tool is None:
            return AgentToolResult(f"Unknown tool `{name}`. Available tools: {', '.join(by_name)}.", False)
        return await tool.execute(arguments)

    conversation = [] if run_messages is None else run_messages
    tool_rounds = 0
    tool_calls = 0
    final_answer_only = False
    while True:
        answer, reasoning, calls, finish_reason = [], [], (), None
        request = prepare_request(messages, conversation)
        async for event in provider.stream_events(request, [] if final_answer_only else definitions):
            if isinstance(event, TextDelta):
                answer.append(event.text)
                yield MessageTextDelta(event.text)
            elif isinstance(event, ReasoningDelta):
                reasoning.append(event.text)
                yield MessageReasoningDelta(event.text)
            elif isinstance(event, TokenUsage):
                yield event
            elif isinstance(event, ToolCallRequest):
                calls = event.calls
            elif isinstance(event, ResponseEnd):
                finish_reason = event.finish_reason
        stop_reason = "length" if finish_reason == "length" else "tool_use" if calls else "stop"
        assistant = AssistantMessage("".join(answer), stop_reason, "".join(reasoning), calls)
        conversation.append(assistant)
        yield MessageEnd(assistant)
        if finish_reason == "length" and calls and not final_answer_only:
            # Arguments cut off mid-stream can still parse as different, valid JSON, so
            # no call from this response runs. The model sees why and can reissue them.
            tool_rounds += 1
            for call in calls:
                yield ToolExecutionStart(call.name, call.arguments, call.id)
                conversation.append(ToolResultMessage(call.id, call.name, TRUNCATED_TOOL_CALL_RESULT, False))
                yield ToolExecutionEnd(call.name, call.arguments, TRUNCATED_TOOL_CALL_RESULT, False, call.id)
            # A refused batch still spends a round, so repeated truncation ends in an answer.
            final_answer_only = max_tool_rounds is not None and tool_rounds >= max_tool_rounds
            continue
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
                outcome = AgentToolResult(
                    "The trusted tool budget is exhausted. Finish with the verified information already available.",
                    False,
                )
                yield ToolExecutionStart(call.name, call.arguments, call.id)
                conversation.append(ToolResultMessage(call.id, call.name, outcome.text, outcome.ok))
                yield ToolExecutionEnd(call.name, call.arguments, outcome.text, outcome.ok, call.id, outcome.details)
            final_answer_only = True
            continue

        tool_rounds += 1
        tool_calls += len(calls)
        batch_scope = activity_batch or _unbatched_activity
        async with batch_scope(calls):
            parallel = len(calls) > 1 and all(
                by_name.get(call.name) is not None and by_name[call.name].read_only for call in calls
            )
            if parallel:
                for call in calls:
                    yield ToolExecutionStart(call.name, call.arguments, call.id)
                started = time.perf_counter()
                outcomes = await _execute_parallel_tool_calls(calls, execute)
                execution_seconds = time.perf_counter() - started
                completed = zip(calls, outcomes, strict=True)
                for call, outcome in completed:
                    _log_tool_outcome(call.name, outcome)
                    conversation.append(ToolResultMessage(call.id, call.name, outcome.text, outcome.ok, outcome.image))
                    yield ToolExecutionEnd(
                        call.name, call.arguments, outcome.text, outcome.ok, call.id, outcome.details
                    )
            else:
                execution_seconds = 0.0
                for call in calls:
                    yield ToolExecutionStart(call.name, call.arguments, call.id)
                    started = time.perf_counter()
                    outcome = await execute(call.name, call.arguments)
                    execution_seconds += time.perf_counter() - started
                    _log_tool_outcome(call.name, outcome)
                    conversation.append(ToolResultMessage(call.id, call.name, outcome.text, outcome.ok, outcome.image))
                    yield ToolExecutionEnd(
                        call.name, call.arguments, outcome.text, outcome.ok, call.id, outcome.details
                    )
            if observe_tool_batch is not None:
                observe_tool_batch(AgentToolBatchMetrics(len(calls), parallel, execution_seconds))
        if take_steering is not None:
            for message_id, text in take_steering(False):
                conversation.append(UserMessage(text))
                yield AgentSteering(message_id, text)


async def _execute_parallel_tool_calls(
    calls: Sequence[ToolCall],
    execute: Callable[[str, str], Awaitable[AgentToolResult]],
) -> list[AgentToolResult]:
    tasks = [asyncio.create_task(execute(call.name, call.arguments)) for call in calls]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def _log_tool_outcome(name: str, outcome: AgentToolResult) -> None:
    logger.info(
        "agent tool call name=%s ok=%s result_chars=%s image_bytes=%s",
        name,
        outcome.ok,
        len(outcome.text),
        len(outcome.image.data) if outcome.image is not None else 0,
    )
