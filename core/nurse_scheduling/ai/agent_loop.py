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
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing, asynccontextmanager
from dataclasses import asdict, replace
from math import ceil

from .agent_types import (
    AgentCompaction,
    AgentCompactionEnd,
    AgentContextUsage,
    AgentEvent,
    AgentGenerationProgress,
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
from .compaction import ContextCompactor
from .config import MAX_HISTORY_CHARS
from .context import compatible_provider_messages, history_chars, prepare_provider_request
from .provider import (
    ChatMessage,
    ProviderCall,
    ProviderContextOverflowError,
    ProviderRetry,
    ReasoningDelta,
    ReasoningReplay,
    ResponseEnd,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallProgress,
    ToolCallRequest,
    ToolCapableChatProvider,
)
from .transcript import AgentMessage, AssistantMessage, CompactionEntry, ToolResultMessage, UserMessage

logger = logging.getLogger("nurse_scheduling.ai.agent")
MAX_PARALLEL_TOOL_CALLS = 16

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
    max_parallel_tools: int = MAX_PARALLEL_TOOL_CALLS,
    run_messages: list[AgentMessage] | None = None,
    history_limit: int = MAX_HISTORY_CHARS,
    reserve_tokens: int = 16384,
    keep_recent_tokens: int = 20000,
) -> AsyncIterator[AgentEvent]:
    """Run the model/tool loop shared by agent capability layers."""
    registered = {tool.name: tool for tool in tools}

    async def execute(name: str, arguments: str) -> AgentToolOutcome:
        tool = registered.get(name)
        if tool is None:
            return AgentToolOutcome(f"Unknown tool `{name}`. Available tools: {', '.join(registered)}.", False)
        return await tool.execute(arguments)

    conversation = [] if run_messages is None else run_messages
    prefix = list(messages)
    tool_rounds = 0
    tool_calls = 0
    final_answer_only = False
    compactor = ContextCompactor(provider, reserve_tokens=reserve_tokens, keep_recent_tokens=keep_recent_tokens)
    await compactor.prepare()
    overflow_recovered = False

    def current_request():
        return prepare_provider_request(prefix, conversation, _preserve_native=True)

    async def compact_context(*, force=False):
        events = compactor.compact(
            current_request(),
            [tool.definition for tool in tools],
            force=force,
            already_compacted=bool(
                conversation and isinstance(conversation[-1], CompactionEntry) and conversation[-1].valid
            ),
            after_omitted_attempt=bool(
                force
                and conversation
                and isinstance(conversation[-1], AssistantMessage)
                and conversation[-1].context_omitted
            ),
        )
        async with aclosing(events):
            async for event in events:
                if isinstance(event, AgentCompaction):
                    conversation.append(event.entry)
                yield event

    while True:
        async with aclosing(compact_context()) as compaction_events:
            async for event in compaction_events:
                yield event
        # Drain after compaction too, since it can receive steering while the
        # summary streams. Every follow-up provider request must see queued input.
        if conversation and take_steering is not None:
            for message_id, text in take_steering(False):
                overflow_recovered = False
                conversation.append(UserMessage(text))
                yield AgentSteering(message_id, text)
        answer, reasoning, calls = [], [], ()
        finish_reason = None
        output_token_limit = None
        output_token_allowance = None
        replay = None
        usage = None
        request = current_request()
        definitions = [] if final_answer_only else [tool.definition for tool in tools]
        request_chars = history_chars([message for message in request if message["role"] != "system"])
        request_tokens = compactor.tokens(request, definitions)
        response_chars = 0
        reported_chars = 0
        yield AgentContextUsage(min(history_limit, request_chars), request_tokens)
        bind_limit = getattr(provider, "with_output_limit", None)
        request_provider = bind_limit(None, context_used_tokens=request_tokens) if bind_limit is not None else provider
        provider_events = request_provider.stream_events(
            compatible_provider_messages(request, getattr(provider, "identity", None)),
            definitions,
        )
        try:
            async with aclosing(provider_events):
                async for event in provider_events:
                    if isinstance(event, TextDelta | ReasoningDelta):
                        response_chars += len(event.text)
                        if isinstance(event, TextDelta):
                            answer.append(event.text)
                            yield AgentText(event.text)
                        else:
                            reasoning.append(event.text)
                            yield AgentReasoning(event.text)
                        yield AgentContextUsage(
                            min(history_limit, request_chars + response_chars),
                            request_tokens + ceil((response_chars - reported_chars) / 4),
                        )
                    elif isinstance(event, ReasoningReplay):
                        replay = event
                    elif isinstance(event, ProviderRetry):
                        # Preserve the failed attempt for audit, but restart from the
                        # original request. Incomplete native output is never replayed.
                        failed = AssistantMessage("".join(answer), "error", "".join(reasoning))
                        conversation.append(failed)
                        yield AgentMessageEnd(failed)
                        answer, reasoning, calls = [], [], ()
                        replay = usage = None
                        finish_reason = None
                        yield event
                    elif isinstance(event, (TokenUsage, ProviderCall)):
                        if isinstance(event, TokenUsage):
                            usage = asdict(event)
                            request_tokens = event.prompt_tokens + event.completion_tokens
                            reported_chars = response_chars
                        yield event
                    elif isinstance(event, ToolCallRequest):
                        calls = event.calls
                    elif isinstance(event, ToolCallProgress):
                        yield AgentGenerationProgress("tool_calls", event.characters)
                    elif isinstance(event, ResponseEnd):
                        finish_reason = event.finish_reason
                        output_token_limit = event.output_token_limit
                        output_token_allowance = event.output_token_allowance
        except ProviderContextOverflowError:
            failed = AssistantMessage(
                "".join(answer), "error", "".join(reasoning), calls, usage=usage, context_omitted=True
            )
            conversation.append(failed)
            yield AgentMessageEnd(failed)
            if overflow_recovered:
                raise
            compacted = False
            async with aclosing(compact_context(force=True)) as compaction_events:
                async for event in compaction_events:
                    compacted = compacted or isinstance(event, AgentCompaction)
                    yield event
            if not compacted:
                raise
            overflow_recovered = True
            continue
        except BaseException as exc:
            reason = "aborted" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else "error"
            conversation.append(AssistantMessage("".join(answer), reason, "".join(reasoning), calls))
            raise
        stop_reason = "length" if finish_reason == "length" else "tool_use" if calls else "stop"
        response = AssistantMessage(
            "".join(answer),
            stop_reason,
            "".join(reasoning),
            calls,
            replay.native if replay else {},
            replay.provider if replay else getattr(provider, "identity", None),
            usage,
        )
        desired_output = output_token_allowance or output_token_limit or getattr(provider, "output_tokens", None)
        completion = (usage or {}).get("completion_tokens")
        recoverable_length = (
            finish_reason == "length"
            and type(desired_output) is int
            and desired_output > 0
            and (
                (type(completion) is int and completion < desired_output)
                or (
                    completion is None
                    and type(output_token_limit) is int
                    and type(output_token_allowance) is int
                    and 0 < output_token_limit < output_token_allowance
                )
            )
        )
        if recoverable_length and overflow_recovered:
            conversation.append(response)
            yield AgentMessageEnd(response)
            yield AgentCompactionEnd("overflow", False, compactor.tokens(current_request(), definitions))
            steering = tuple(take_steering(True)) if take_steering is not None else ()
            for message_id, text in steering:
                overflow_recovered = False
                conversation.append(UserMessage(text))
                yield AgentSteering(message_id, text)
            if steering:
                continue
            break
        if recoverable_length:
            # Keep the truncated attempt for audit, but omit it from the context
            # being summarized and retried. Never execute its partial tool calls.
            # Compaction events checkpoint the attempt before summary calls. Publish
            # the omission only after a summary succeeds and a retry can replace it.
            response_index = len(conversation)
            omitted = replace(response, context_omitted=True)
            conversation.append(omitted)
            compacted = False
            async with aclosing(compact_context(force=True)) as compaction_events:
                async for event in compaction_events:
                    compacted = compacted or isinstance(event, AgentCompaction)
                    yield event
            if compacted:
                yield AgentMessageEnd(omitted)
                overflow_recovered = True
                continue
            conversation[response_index] = response
        else:
            conversation.append(response)
        overflow_recovered = False
        yield AgentMessageEnd(response)
        if not calls:
            async with aclosing(compact_context()) as compaction_events:
                async for event in compaction_events:
                    yield event
            steering = tuple(take_steering(True)) if take_steering is not None else ()
            if not steering:
                break
            for message_id, text in steering:
                overflow_recovered = False
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
                yield _record_tool_result(
                    conversation,
                    call,
                    AgentToolOutcome(TRUNCATED_TOOL_CALL_RESULT, False, details={"replay_arguments": "{}"}),
                )
            final_answer_only = (max_tool_rounds is not None and tool_rounds >= max_tool_rounds) or (
                max_tool_calls is not None and tool_calls >= max_tool_calls
            )
            continue
        batch_scope = activity_batch or _unbatched_activity
        async with batch_scope():
            terminal = False
            end_turn_message = None
            completed_calls = 0
            parallel = len(calls) > 1 and all(
                call.name in registered and registered[call.name].read_only for call in calls
            )
            if parallel:
                for call in calls:
                    yield AgentToolStart(call.name, call.arguments, call.id)
                started = time.perf_counter()
                outcomes = await _execute_parallel_tool_calls(calls, execute, max_parallel_tools)
                execution_seconds = time.perf_counter() - started
                completed = zip(calls, outcomes, strict=True)
                for call, outcome in completed:
                    yield _record_tool_result(conversation, call, outcome)
                    completed_calls += 1
                    terminal = terminal or outcome.terminal
                    end_turn_message = end_turn_message or outcome.end_turn_message
            else:
                execution_seconds = 0.0
                for index, call in enumerate(calls):
                    yield AgentToolStart(call.name, call.arguments, call.id)
                    started = time.perf_counter()
                    outcome = await execute(call.name, call.arguments)
                    execution_seconds += time.perf_counter() - started
                    yield _record_tool_result(conversation, call, outcome)
                    completed_calls += 1
                    terminal = terminal or outcome.terminal
                    end_turn_message = outcome.end_turn_message
                    if terminal:
                        break
                    if end_turn_message is not None:
                        for skipped in calls[index + 1 :]:
                            yield AgentToolStart(skipped.name, skipped.arguments, skipped.id)
                            yield _record_tool_result(
                                conversation,
                                skipped,
                                AgentToolOutcome(
                                    "This call was not executed because the previous tool ended the assistant turn.",
                                    False,
                                ),
                            )
                        break
            if observe_tool_batch is not None:
                observe_tool_batch(AgentToolBatchMetrics(completed_calls, parallel, execution_seconds))
        if terminal:
            return
        if end_turn_message is not None:
            closing = AssistantMessage(end_turn_message)
            conversation.append(closing)
            yield AgentText(end_turn_message)
            yield AgentMessageEnd(closing)
            async with aclosing(compact_context()) as compaction_events:
                async for event in compaction_events:
                    yield event
            steering = tuple(take_steering(True)) if take_steering is not None else ()
            if not steering:
                return
            for message_id, text in steering:
                overflow_recovered = False
                conversation.append(UserMessage(text))
                yield AgentSteering(message_id, text)


def _record_tool_result(conversation: list[AgentMessage], call: ToolCall, outcome: AgentToolOutcome) -> AgentToolUse:
    """Record the provider result once before publishing its completion."""
    _log_tool_outcome(call.name, outcome)
    conversation.append(ToolResultMessage(call.id, call.name, outcome.text, outcome.ok, outcome.image))
    return AgentToolUse(call.name, call.arguments, outcome.text, outcome.ok, call.id, outcome.details)


async def _execute_parallel_tool_calls(
    calls: Sequence[ToolCall],
    execute: ToolExecutor,
    max_parallel_tools: int,
) -> list[AgentToolOutcome]:
    semaphore = asyncio.Semaphore(max_parallel_tools)

    async def bounded_execute(call: ToolCall) -> AgentToolOutcome:
        async with semaphore:
            return await execute(call.name, call.arguments)

    tasks = [asyncio.create_task(bounded_execute(call)) for call in calls]
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
