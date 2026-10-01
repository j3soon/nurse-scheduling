"""Run the evaluation cases against the configured provider and report results."""

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

# This test is mostly AI generated.

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from nurse_scheduling.ai.agent import (
    AgentProposal,
    AgentReasoning,
    AgentText,
    AgentToolBatchMetrics,
    AgentToolOutcome,
    AgentToolStart,
    AgentToolUse,
)
from nurse_scheduling.ai.app import PROPOSAL_APPROVED_HISTORY, PROPOSAL_REJECTED_HISTORY, build_provider_messages
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ChatStreamEvent,
    OpenAiCompatibleProvider,
    ProviderAttempt,
    ProviderError,
    TokenUsage,
    ToolCallRequest,
)
from nurse_scheduling.ai.sandbox import SandboxError, SandboxFactory, managed_sandbox_factory
from nurse_scheduling.ai.sandbox.factory import create_sandbox_factory
from nurse_scheduling.ai.sandbox_agent import (
    SANDBOX_SYSTEM_PROMPT,
    SandboxAgentLimits,
    SandboxTurnMetrics,
    run_sandbox_agent,
)
from nurse_scheduling.ai.schema import (
    SCHEMA_REFERENCE_FILES,
    TAIWAN_HOLIDAYS_SOURCE,
    load_schedule_reference,
    load_taiwan_holidays_reference,
    load_user_guide_references,
)
from nurse_scheduling.loader import _load_yaml

from .attachment_fixtures import load_attachment_fixtures
from .grading import (
    EvalCase,
    RunOutcome,
    computed_values,
    grade,
    load_cases,
    semantic_trajectory_failures,
    tool_limit_failures,
)
from .prompt_ladder import case_digest, load_prompt_steps, prompt_at_step

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CASES = Path(__file__).resolve().parent / "cases"
FIXTURES = {
    "cross-year-unit": Path(__file__).resolve().parent / "fixtures" / "cross-year-unit.yaml",
    "new-schedule": Path(__file__).resolve().parent / "fixtures" / "new-schedule.yaml",
    "small-clinic": Path(__file__).resolve().parent / "fixtures" / "small-clinic.yaml",
    "ward87": Path(__file__).resolve().parents[1] / "testcases" / "real",
}
WARD_FILE = "large-ward-with-87-people-2025-11.yaml"
DEFAULT_CASE_JOBS = 4
DEFAULT_CASE_TAGS = {"difficult", "tuning"}


@dataclass
class CaseRun:
    """What one case produced, with enough detail to explain a failure."""

    case_id: str
    category: str
    passed: bool
    seconds: float
    turns: int
    tools: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    answer: str = ""
    proposed: bool = False
    reasoning_chars: int = 0
    error: str = ""
    trajectory: dict[str, Any] = field(default_factory=dict)
    token_usage: TokenUsage | None = None
    token_usage_turns: int = 0
    llm_inference_seconds: float = 0.0
    llm_turn_seconds: list[float] = field(default_factory=list)
    sandbox_metrics: SandboxTurnMetrics | None = None
    provider_attempts: int = 0
    provider_attempts_per_turn: list[int] = field(default_factory=list)
    tool_calls_per_turn: list[int] = field(default_factory=list)
    tool_batch_metrics: list[AgentToolBatchMetrics] = field(default_factory=list)
    repetition: int = 1
    prompt_variant: str = "production"

    def as_record(self) -> dict[str, Any]:
        """Render one result as a line of the report."""
        return {
            "case_id": self.case_id,
            "repetition": self.repetition,
            "prompt_variant": self.prompt_variant,
            "category": self.category,
            "passed": self.passed,
            "seconds": round(self.seconds, 1),
            "timing": _timing_record(
                self.seconds,
                self.llm_inference_seconds,
                self.llm_turn_seconds,
                self.sandbox_metrics,
            ),
            "turns": self.turns,
            "tools": self.tools,
            "failures": self.failures,
            "proposed": self.proposed,
            "reasoning_chars": self.reasoning_chars,
            "answer": self.answer,
            "error": self.error,
            "token_usage": _token_usage_record(self.token_usage, self.token_usage_turns, self.turns),
            "provider_requests": _provider_request_record(
                self.turns,
                self.provider_attempts,
                self.provider_attempts_per_turn,
            ),
            "tool_batches": _tool_batch_record(self.tool_calls_per_turn, self.tool_batch_metrics),
        }

    def as_trajectory(self) -> dict[str, Any]:
        """Render everything one case did, for reading back a failure."""
        return {**self.as_record(), **self.trajectory}


class _CountingProvider:
    """Forward to the real provider while counting the turns one answer took."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.turns = 0
        self.token_usage: TokenUsage | None = None
        self.token_usage_turns = 0
        self.inference_seconds = 0.0
        self.inference_turn_seconds: list[float] = []
        self.attempts = 0
        self.attempts_per_turn: list[int] = []
        self.tool_calls_per_turn: list[int] = []

    async def stream_events(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self.turns += 1
        stream = self._provider.stream_events(messages, tools).__aiter__()
        turn_seconds = 0.0
        turn_attempts = 0
        turn_tool_calls = 0
        try:
            while True:
                started = time.perf_counter()
                try:
                    event = await anext(stream)
                except StopAsyncIteration:
                    break
                finally:
                    elapsed = time.perf_counter() - started
                    self.inference_seconds += elapsed
                    turn_seconds += elapsed
                if isinstance(event, TokenUsage):
                    self.token_usage = event if self.token_usage is None else self.token_usage + event
                    self.token_usage_turns += 1
                    continue
                if isinstance(event, ProviderAttempt):
                    turn_attempts += 1
                    continue
                if isinstance(event, ToolCallRequest):
                    turn_tool_calls += len(event.calls)
                yield event
        finally:
            if turn_attempts == 0:
                turn_attempts = 1
            self.attempts += turn_attempts
            self.attempts_per_turn.append(turn_attempts)
            self.tool_calls_per_turn.append(turn_tool_calls)
            self.inference_turn_seconds.append(turn_seconds)
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()


def fixture_text(fixture: str) -> str:
    """Read a named starting schedule used by evaluation cases."""
    path = FIXTURES[fixture]
    return (path / WARD_FILE if path.is_dir() else path).read_text(encoding="utf-8")


async def run_case(
    provider: Any,
    settings: AiSettings,
    case: EvalCase,
    sandbox_factory: SandboxFactory | None = None,
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    fail_fast: bool = True,
) -> CaseRun:
    """Answer one case the way the service would, then grade what it produced."""
    text = fixture_text(case.fixture)
    initial_text = text
    counting = _CountingProvider(provider)

    history: list[ChatMessage] = []
    prompt_messages: list[list[ChatMessage]] = []
    answers: list[str] = []
    intermediate_proposals: list[bool] = []
    proposal_turns: list[bool] = []
    tools: list[str] = []
    events: list[dict[str, Any]] = []
    proposal_event: AgentProposal | None = None
    pending_proposal: AgentProposal | None = None
    turn_actions = {action.after_turn: action for action in case.turn_actions}
    sandbox_metrics = SandboxTurnMetrics()
    tool_batch_metrics: list[AgentToolBatchMetrics] = []
    reasoning = 0
    started = time.perf_counter()
    case_attachments = load_attachment_fixtures(case.attachments)
    optimizer_started = False

    async def execute_optimizer(_schedule_yaml: str, arguments: str) -> AgentToolOutcome:
        """Expose the production tool contract without submitting an actual job."""
        nonlocal optimizer_started
        try:
            request = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return AgentToolOutcome("Optimizer arguments must be valid JSON.", False)
        if not isinstance(request, dict):
            return AgentToolOutcome("Optimizer arguments must be an object.", False)
        if case.optimizer_error:
            return AgentToolOutcome(case.optimizer_error, False)
        action = request.get("action", "start")
        if action == "start":
            timeout = request.get("timeout_seconds")
            if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0):
                return AgentToolOutcome("timeout_seconds must be a positive integer.", False)
            if optimizer_started:
                return AgentToolOutcome("An optimizer run is already running for this chat session.", False)
            optimizer_started = True
            return AgentToolOutcome(
                "Started optimizer job eval-job in the background. The user can keep chatting.", True
            )
        if action == "status" and optimizer_started:
            return AgentToolOutcome("Optimizer job eval-job is running.", True)
        if action == "finish_now" and optimizer_started:
            return AgentToolOutcome("Asked optimizer job eval-job to finish now.", True)
        if action not in {"start", "status", "finish_now"}:
            return AgentToolOutcome("action must be one of: start, status, finish_now.", False)
        return AgentToolOutcome("No optimizer job has been started in this chat session.", False)

    try:
        if sandbox_factory is None:
            raise ValueError("sandbox_factory is required for AI evaluation")
        for turn_index, question in enumerate(case.user_turns):
            attachments = case_attachments if turn_index == 0 else ()
            messages = build_provider_messages(
                history,
                text,
                question,
                attachments,
                system_prompt=system_prompt,
                pending_proposal=pending_proposal is not None,
            )
            prompt_messages.append(messages)
            turn_answer: list[str] = []
            turn_proposal: AgentProposal | None = None
            stopped_on_limit = False
            turn_event_offset = len(events)
            events.append({"kind": "user", "turn": turn_index + 1, "text": question})
            agent_events = run_sandbox_agent(
                counting,
                sandbox_factory,
                text,
                messages,
                SandboxAgentLimits.from_settings(settings),
                sandbox_metrics,
                tool_batch_metrics.append,
                pending_proposal_yaml=pending_proposal.text if pending_proposal else "",
                pending_proposal_diff=pending_proposal.diff if pending_proposal else "",
                execute_optimizer=execute_optimizer,
                attachments=attachments,
            )
            async with aclosing(agent_events):
                async for event in agent_events:
                    if isinstance(event, AgentText):
                        turn_answer.append(event.text)
                        _record_text(events, "text", event.text)
                    elif isinstance(event, AgentReasoning):
                        reasoning += len(event.text)
                        _record_text(events, "reasoning", event.text)
                    elif isinstance(event, AgentToolStart):
                        events.append({"kind": "tool_start", "name": event.name, "arguments": event.arguments})
                        if fail_fast and (failures := semantic_trajectory_failures(case, events)):
                            events.append(
                                {
                                    "kind": "evaluation_stop",
                                    "turn": turn_index + 1,
                                    "reason": _describe(failures[0]),
                                }
                            )
                            stopped_on_limit = True
                            break
                    elif isinstance(event, AgentToolUse):
                        tools.append(event.name if event.ok else f"{event.name}(failed)")
                        events.append(
                            {
                                "kind": "tool",
                                "name": event.name,
                                "ok": event.ok,
                                "arguments": event.arguments,
                                "result": event.result,
                            }
                        )
                        if fail_fast:
                            turn_limit = (
                                case.turn_tool_usage[turn_index] if turn_index < len(case.turn_tool_usage) else None
                            )
                            for expected, activity in (
                                (case.tool_usage, events),
                                (turn_limit, events[turn_event_offset:]),
                            ):
                                failures = tool_limit_failures(activity, expected) if expected is not None else ()
                                if failures:
                                    events.append(
                                        {
                                            "kind": "evaluation_stop",
                                            "turn": turn_index + 1,
                                            "reason": _describe(failures[0]),
                                        }
                                    )
                                    stopped_on_limit = True
                                    break
                        if stopped_on_limit:
                            break
                    elif isinstance(event, AgentProposal):
                        turn_proposal = event
                        events.append({"kind": "proposal", "diff": event.diff})
            answer_text = "".join(turn_answer)
            answers.append(answer_text)
            proposal_turns.append(turn_proposal is not None)
            if turn_proposal is not None:
                pending_proposal = turn_proposal
            if turn_index < len(case.user_turns) - 1:
                intermediate_proposals.append(turn_proposal is not None)
            if turn_index + 1 == case.proposal_turn:
                proposal_event = turn_proposal
            history.extend(
                [ChatMessage(role="user", content=question), ChatMessage(role="assistant", content=answer_text)]
            )
            if stopped_on_limit:
                break
            if fail_fast and turn_proposal is not None and turn_index + 1 not in case.proposal_turns:
                events.append({"kind": "evaluation_stop", "turn": turn_index + 1, "reason": "unexpected proposal"})
                break
            action = turn_actions.get(turn_index + 1)
            if action is not None:
                text, pending_proposal = _apply_turn_action(action, text, pending_proposal, history, events)
    except (ProviderError, SandboxError) as error:
        failure = "the provider failed" if isinstance(error, ProviderError) else "the sandbox failed"
        return CaseRun(
            case.id,
            case.category,
            False,
            time.perf_counter() - started,
            counting.turns,
            tools,
            [failure],
            answers[-1] if answers else "",
            False,
            reasoning,
            str(error),
            _trajectory(case, prompt_messages, events, None),
            token_usage=counting.token_usage,
            token_usage_turns=counting.token_usage_turns,
            llm_inference_seconds=counting.inference_seconds,
            llm_turn_seconds=counting.inference_turn_seconds,
            sandbox_metrics=sandbox_metrics,
            provider_attempts=counting.attempts,
            provider_attempts_per_turn=counting.attempts_per_turn,
            tool_calls_per_turn=counting.tool_calls_per_turn,
            tool_batch_metrics=tool_batch_metrics,
        )

    elapsed = time.perf_counter() - started
    initial = _load_yaml(initial_text.encode("utf-8"))
    proposed = _load_yaml(proposal_event.text.encode("utf-8")) if proposal_event else None
    outcome = RunOutcome(
        answer=answers[-1] if answers else "",
        proposed=proposed,
        initial=initial,
        activity=events,
        intermediate_answers=answers[: len(case.user_turns) - 1],
        intermediate_proposals=intermediate_proposals,
        proposal_turns=proposal_turns,
    )
    result = grade(case, outcome, computed_values(initial))
    return CaseRun(
        case_id=case.id,
        category=case.category,
        passed=result.passed,
        seconds=elapsed,
        turns=counting.turns,
        tools=tools,
        failures=[_describe(failure) for failure in result.failures()],
        answer=outcome.answer,
        proposed=proposed is not None,
        reasoning_chars=reasoning,
        trajectory=_trajectory(case, prompt_messages, events, proposal_event, result),
        token_usage=counting.token_usage,
        token_usage_turns=counting.token_usage_turns,
        llm_inference_seconds=counting.inference_seconds,
        llm_turn_seconds=counting.inference_turn_seconds,
        sandbox_metrics=sandbox_metrics,
        provider_attempts=counting.attempts,
        provider_attempts_per_turn=counting.attempts_per_turn,
        tool_calls_per_turn=counting.tool_calls_per_turn,
        tool_batch_metrics=tool_batch_metrics,
    )


def _record_text(events: list[dict[str, Any]], kind: str, text: str) -> None:
    """Join consecutive fragments, so the record reads as what the model wrote."""
    if events and events[-1]["kind"] == kind:
        events[-1]["text"] += text
        return
    events.append({"kind": kind, "text": text})


def _apply_turn_action(
    action: Any,
    text: str,
    pending: AgentProposal | None,
    history: list[ChatMessage],
    events: list[dict[str, Any]],
) -> tuple[str, AgentProposal | None]:
    """Apply one trusted proposal lifecycle action between user turns."""
    if action.action in {"approve", "reject"} and pending is None:
        events.append({"kind": "turn_action", "turn": action.after_turn, "action": action.action, "ok": False})
        return text, None
    if action.action == "approve":
        text = pending.text
        history.append(ChatMessage(role="user", content=PROPOSAL_APPROVED_HISTORY))
    elif action.action == "reject":
        history.append(ChatMessage(role="user", content=PROPOSAL_REJECTED_HISTORY))
    else:
        schedule = _load_yaml(text.encode("utf-8"))
        schedule.update(dict(action.schedule_patch))
        stream = StringIO()
        YAML().dump(schedule, stream)
        text = stream.getvalue()
    events.append({"kind": "turn_action", "turn": action.after_turn, "action": action.action, "ok": True})
    return text, None


def _trajectory(
    case: EvalCase,
    messages: Sequence[Sequence[ChatMessage]],
    events: list[dict[str, Any]],
    proposal: Any,
    result: Any = None,
) -> dict[str, Any]:
    """Collect the question, the prompt, and everything the run did."""
    return {
        "fixture": case.fixture,
        "question": case.question,
        "user_turns": list(case.user_turns),
        "proposal_turns": list(case.proposal_turns),
        "turn_actions": [
            {
                "after_turn": action.after_turn,
                "action": action.action,
                "schedule_patch": dict(action.schedule_patch),
            }
            for action in case.turn_actions
        ],
        "tags": list(case.tags),
        "note": case.note,
        "prompt": [dict(message) for message in messages[0]] if messages else [],
        "prompts": [[dict(message) for message in turn] for turn in messages],
        "reasoning": "".join(event["text"] for event in events if event["kind"] == "reasoning"),
        "events": events,
        "checks": [
            {"description": check.description, "passed": check.passed, "detail": check.detail}
            for check in (result.checks if result else ())
        ],
        "proposal": {
            "schedule_yaml": proposal.text,
            "diff": proposal.diff if isinstance(proposal.diff, str) else proposal.diff.render(),
        }
        if proposal
        else None,
    }


def _describe(failure: Any) -> str:
    """Render one failed check for the report."""
    return f"{failure.description}: {failure.detail}" if failure.detail else failure.description


def _token_usage_record(usage: TokenUsage | None, reported_turns: int, turns: int) -> dict[str, Any]:
    """Render exact provider usage, or make its absence explicit."""
    return {
        "available": usage is not None,
        "complete": turns > 0 and reported_turns == turns,
        "reported_turns": reported_turns,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "cached_prompt_tokens": usage.cached_prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
        "reasoning_tokens": usage.reasoning_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
    }


def _provider_request_record(turns: int, attempts: int, attempts_per_turn: Sequence[int]) -> dict[str, Any]:
    """Separate logical model turns from retried HTTP requests."""
    effective_attempts = attempts or turns
    effective_per_turn = list(attempts_per_turn) or [1] * turns
    return {
        "turns": turns,
        "attempts": effective_attempts,
        "retries": max(0, effective_attempts - turns),
        "retried_turns": sum(attempts > 1 for attempts in effective_per_turn),
        "attempts_per_turn": effective_per_turn,
    }


def _tool_batch_record(
    tool_calls_per_turn: Sequence[int],
    metrics: Sequence[AgentToolBatchMetrics] = (),
) -> dict[str, Any]:
    """Describe the model turns that requested one or more tools."""
    calls_per_batch = [count for count in tool_calls_per_turn if count > 0]
    return {
        "count": len(calls_per_batch),
        "multi_call_batches": sum(count > 1 for count in calls_per_batch),
        "max_calls_per_batch": max(calls_per_batch, default=0),
        "calls_per_batch": calls_per_batch,
        "calls_per_turn": list(tool_calls_per_turn),
        "parallel_batches": sum(metric.parallel for metric in metrics),
        "parallel_per_batch": [metric.parallel for metric in metrics],
        "execution_seconds_per_batch": [round(metric.execution_seconds, 3) for metric in metrics],
    }


def _timing_record(
    end_to_end_seconds: float,
    llm_inference_seconds: float,
    llm_turn_seconds: Sequence[float],
    sandbox: SandboxTurnMetrics | None,
) -> dict[str, Any]:
    """Separate overlapping provider and provisioned-sandbox wall times."""
    return {
        "end_to_end_seconds": round(end_to_end_seconds, 3),
        "llm_inference_seconds": round(llm_inference_seconds, 3),
        "llm_turn_seconds": [round(seconds, 3) for seconds in llm_turn_seconds],
        "sandbox": {
            "available": sandbox is not None,
            "lifetime_seconds": round(sandbox.lifetime_seconds, 3) if sandbox else None,
            "provisioning_seconds": round(sandbox.provisioning_seconds, 3) if sandbox else None,
            "execution_seconds": round(sandbox.execution_seconds, 3) if sandbox else None,
            "pause_transition_seconds": round(sandbox.pause_transition_seconds, 3) if sandbox else None,
            "warm_waiting_seconds": round(sandbox.warm_waiting_seconds, 3) if sandbox else None,
            "suspended_seconds": round(sandbox.suspended_seconds, 3) if sandbox else None,
            "resume_wait_seconds": round(sandbox.resume_wait_seconds, 3) if sandbox else None,
            "max_resume_wait_seconds": round(sandbox.max_resume_wait_seconds, 3) if sandbox else None,
            "teardown_seconds": round(sandbox.teardown_seconds, 3) if sandbox else None,
            "suspension": {
                "pause_count": sandbox.pause_count if sandbox else None,
                "pause_cancel_count": sandbox.pause_cancel_count if sandbox else None,
                "resume_count": sandbox.resume_count if sandbox else None,
            },
        },
    }


def summarize(runs: Sequence[CaseRun]) -> str:
    """Report the pass rate and cost of a run, by category and overall."""
    if not runs:
        return "No cases ran."
    lines = [
        (
            f"{'category':<16}{'pass':>8}{'e2e s':>9}{'LLM s':>9}{'lifetime s':>11}"
            f"{'execute s':>10}{'warm wait':>10}{'suspend s':>10}{'resume s':>10}"
            f"{'pauses':>8}{'cancels':>9}{'turns':>8}{'batches':>9}{'multi':>7}"
            f"{'attempts':>10}{'retries':>9}{'tools':>8}"
        )
    ]
    for category in sorted({run.category for run in runs}):
        group = [run for run in runs if run.category == category]
        lines.append(
            f"{category:<16}{sum(run.passed for run in group):>4}/{len(group):<3}"
            f"{_median([run.seconds for run in group]):>9.1f}"
            f"{_median([run.llm_inference_seconds for run in group]):>9.1f}"
            f"{_median([run.sandbox_metrics.lifetime_seconds for run in group if run.sandbox_metrics]):>11.1f}"
            f"{_median([run.sandbox_metrics.execution_seconds for run in group if run.sandbox_metrics]):>10.1f}"
            f"{_median([run.sandbox_metrics.warm_waiting_seconds for run in group if run.sandbox_metrics]):>10.1f}"
            f"{_median([run.sandbox_metrics.suspended_seconds for run in group if run.sandbox_metrics]):>10.1f}"
            f"{_median([run.sandbox_metrics.resume_wait_seconds for run in group if run.sandbox_metrics]):>10.1f}"
            f"{_median([float(run.sandbox_metrics.pause_count) for run in group if run.sandbox_metrics]):>8.1f}"
            f"{_median([float(run.sandbox_metrics.pause_cancel_count) for run in group if run.sandbox_metrics]):>9.1f}"
            f"{_median([float(run.turns) for run in group]):>8.1f}"
            f"{_median([float(sum(count > 0 for count in run.tool_calls_per_turn)) for run in group]):>9.1f}"
            f"{_median([float(sum(count > 1 for count in run.tool_calls_per_turn)) for run in group]):>7.1f}"
            f"{_median([float(run.provider_attempts or run.turns) for run in group]):>10.1f}"
            f"{_median([float(max(0, (run.provider_attempts or run.turns) - run.turns)) for run in group]):>9.1f}"
            f"{_median([float(len(run.tools)) for run in group]):>8.1f}"
        )
    total = sum(run.passed for run in runs)
    sandbox_runs = [run.sandbox_metrics for run in runs if run.sandbox_metrics is not None]
    lines.append(
        f"{'total':<16}{total:>4}/{len(runs):<3}"
        f"{sum(run.seconds for run in runs):>9.1f}"
        f"{sum(run.llm_inference_seconds for run in runs):>9.1f}"
        f"{sum(metrics.lifetime_seconds for metrics in sandbox_runs):>11.1f}"
        f"{sum(metrics.execution_seconds for metrics in sandbox_runs):>10.1f}"
        f"{sum(metrics.warm_waiting_seconds for metrics in sandbox_runs):>10.1f}"
        f"{sum(metrics.suspended_seconds for metrics in sandbox_runs):>10.1f}"
        f"{sum(metrics.resume_wait_seconds for metrics in sandbox_runs):>10.1f}"
        f"{sum(metrics.pause_count for metrics in sandbox_runs):>8}"
        f"{sum(metrics.pause_cancel_count for metrics in sandbox_runs):>9}"
        f"{sum(run.turns for run in runs):>8}"
        f"{sum(count > 0 for run in runs for count in run.tool_calls_per_turn):>9}"
        f"{sum(count > 1 for run in runs for count in run.tool_calls_per_turn):>7}"
        f"{sum(run.provider_attempts or run.turns for run in runs):>10}"
        f"{sum(max(0, (run.provider_attempts or run.turns) - run.turns) for run in runs):>9}"
        f"{sum(len(run.tools) for run in runs):>8}"
    )
    lines.append("Category timing rows are medians. The total row contains sums.")
    failed = [run for run in runs if not run.passed]
    if failed:
        lines.append("")
        lines.append("failures:")
        lines.extend(f"  {run.case_id}: {'; '.join(run.failures) or run.error}" for run in failed)
    return "\n".join(lines)


def stability_markdown(runs: Sequence[CaseRun]) -> str:
    """Show repeated reliability and tail cost for each selected case."""
    if not runs or max(run.repetition for run in runs) == 1:
        return ""
    lines = [
        "## Stability by case",
        "",
        "Infrastructure failures are shown separately but remain failed attempts.",
        "",
        "| Case | Pass rate | Infrastructure | Median turns | p95 turns | Median tokens | p95 tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case_id in sorted({run.case_id for run in runs}):
        group = [run for run in runs if run.case_id == case_id]
        turns = [float(run.turns) for run in group]
        tokens = [float(run.token_usage.total_tokens) for run in group if run.token_usage is not None]
        infrastructure = sum(bool(run.error) for run in group)
        lines.append(
            f"| {case_id} | {sum(run.passed for run in group)}/{len(group)} | {infrastructure} "
            f"| {_median(turns):.1f} | {_percentile(turns, 0.95):.1f} "
            f"| {_median(tokens):.0f} | {_percentile(tokens, 0.95):.0f} |"
        )
    return "\n".join(lines)


def sandbox_metrics_markdown(runs: Sequence[CaseRun]) -> str:
    """Render every sandbox timing field for each case in the Markdown report."""
    sandbox_runs = [(run, run.sandbox_metrics) for run in runs if run.sandbox_metrics is not None]
    if not sandbox_runs:
        return "## Sandbox metrics\n\nNo sandbox metrics were available for this run."

    lines = [
        "## Sandbox timing by case",
        "",
        "Durations are seconds. All columns after lifetime are mutually exclusive lifetime components.",
        "",
        "| Case | Lifetime | Provision | Execute | Pause transition | Warm wait | Suspended | Resume wait | Teardown |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run, metrics in sandbox_runs:
        lines.append(
            f"| {run.case_id} | {metrics.lifetime_seconds:.3f} | {metrics.provisioning_seconds:.3f} "
            f"| {metrics.execution_seconds:.3f} | {metrics.pause_transition_seconds:.3f} "
            f"| {metrics.warm_waiting_seconds:.3f} | {metrics.suspended_seconds:.3f} "
            f"| {metrics.resume_wait_seconds:.3f} | {metrics.teardown_seconds:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Sandbox suspension by case",
            "",
            "| Case | Pauses | Pause cancels | Resumes | Total resume wait | Max resume wait |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for run, metrics in sandbox_runs:
        lines.append(
            f"| {run.case_id} | {metrics.pause_count} | {metrics.pause_cancel_count} | {metrics.resume_count} "
            f"| {metrics.resume_wait_seconds:.3f} | {metrics.max_resume_wait_seconds:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Tool batches by case",
            "",
            "Calls per batch excludes final-answer turns that requested no tools.",
            "",
            "| Case | Batches | Multi-call batches | Max calls | Calls per batch | Parallel batches | Execution seconds per batch |",
            "| --- | ---: | ---: | ---: | --- | ---: | --- |",
        ]
    )
    for run in runs:
        batch = _tool_batch_record(run.tool_calls_per_turn, run.tool_batch_metrics)
        calls = ", ".join(str(count) for count in batch["calls_per_batch"]) or "none"
        durations = ", ".join(f"{seconds:.3f}" for seconds in batch["execution_seconds_per_batch"]) or "none"
        lines.append(
            f"| {run.case_id} | {batch['count']} | {batch['multi_call_batches']} "
            f"| {batch['max_calls_per_batch']} | {calls} | {batch['parallel_batches']} | {durations} |"
        )
    return "\n".join(lines)


def default_output_dir() -> Path:
    """Give each run its own timestamped directory, as the performance benchmark does."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = Path(os.environ.get("AI_EVAL_ARTIFACT_ROOT", REPOSITORY_ROOT / "artifacts"))
    return artifact_root / "ai-evals" / timestamp


def write_report(
    runs: Sequence[CaseRun],
    output_dir: Path,
    *,
    jobs: int = 1,
    wall_seconds: float | None = None,
    metadata: dict[str, Any] | None = None,
    baseline_report: Path | None = None,
) -> Path:
    """Write one run's results and summary, and report where the summary landed."""
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "results.jsonl").write_text(
        "".join(json.dumps(run.as_record(), ensure_ascii=False) + "\n" for run in runs), encoding="utf-8"
    )
    # One file per case, so a failure can be read back in full.
    cases_dir = output_dir / "cases"
    cases_dir.mkdir()
    repeated = max((run.repetition for run in runs), default=1) > 1
    for run in runs:
        suffix = f"--run-{run.repetition}" if repeated else ""
        (cases_dir / f"{run.case_id}{suffix}.json").write_text(
            json.dumps(run.as_trajectory(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if metadata is not None:
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    summary = output_dir / "summary.md"
    timing = f"\nWall time: {wall_seconds:.1f} seconds\n" if wall_seconds is not None else ""
    stability = stability_markdown(runs)
    comparison = comparison_markdown(_load_report_records(baseline_report), runs) if baseline_report else ""
    stability_section = f"{stability}\n\n" if stability else ""
    comparison_section = f"{comparison}\n\n" if comparison else ""
    summary.write_text(
        f"# AI evaluation\n\nCase concurrency: {jobs}{timing}\n"
        f"## Aggregate\n\n```\n{summarize(runs)}\n```\n"
        f"{stability_section}"
        f"{comparison_section}"
        f"{sandbox_metrics_markdown(runs)}\n",
        encoding="utf-8",
    )
    return summary


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return 0.0
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile, or zero for no observations."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))]


def _load_report_records(path: Path) -> list[dict[str, Any]]:
    results = path / "results.jsonl" if path.is_dir() else path
    return [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]


def comparison_markdown(baseline: Sequence[dict[str, Any]], current: Sequence[CaseRun]) -> str:
    """Compare reliability and cost with a prior JSONL report."""
    lines = [
        "## Baseline comparison",
        "",
        "| Case | Baseline pass | Current pass | Pass delta | Turn delta | Token delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    current_ids = {run.case_id for run in current}
    baseline_ids = {str(record["case_id"]) for record in baseline}
    for case_id in sorted(current_ids & baseline_ids):
        before = [record for record in baseline if record["case_id"] == case_id]
        after = [run for run in current if run.case_id == case_id]
        before_rate = sum(bool(record["passed"]) for record in before) / len(before)
        after_rate = sum(run.passed for run in after) / len(after)
        before_turns = _median([float(record["turns"]) for record in before])
        after_turns = _median([float(run.turns) for run in after])
        before_tokens = _median(
            [float(record["token_usage"]["total_tokens"]) for record in before if record["token_usage"]["total_tokens"]]
        )
        after_tokens = _median([float(run.token_usage.total_tokens) for run in after if run.token_usage is not None])
        lines.append(
            f"| {case_id} | {before_rate:.0%} | {after_rate:.0%} | {after_rate - before_rate:+.0%} "
            f"| {after_turns - before_turns:+.1f} | {after_tokens - before_tokens:+.0f} |"
        )
    return "\n".join(lines)


def _prompt_cost(run: CaseRun, metric: str) -> float | None:
    """Count cost only for a completed, correct case run."""
    if not run.passed or run.error:
        return None
    if metric == "tool-calls":
        return float(len(run.tools))
    if metric == "turns":
        return float(run.turns)
    if metric == "seconds":
        return run.seconds
    if metric == "uncached-tokens" and run.token_usage is not None and run.token_usage_turns == run.turns:
        return float(run.token_usage.prompt_tokens - run.token_usage.cached_prompt_tokens)
    return None


def prompt_comparison_markdown(
    runs: Sequence[CaseRun], metric: str | None = None, max_ratio: float | None = None
) -> tuple[str, bool]:
    """Require a clean correctness gain or an explicit relative cost gain."""
    case_ids = sorted({run.case_id for run in runs})
    lines = [
        "# Prompt comparison",
        "",
        "Infrastructure errors make the comparison inconclusive. Cost is compared only when every attempt passes.",
        "A passing result is directional evidence, not a statistical guarantee.",
        "",
        "| Case | Before pass | After pass | Infrastructure | Cost ratio |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    all_after_pass = True
    any_correctness_gain = False
    any_cost_gain = False
    cost_regression = False
    cost_missing = False
    any_correctness_regression = False
    clean = True
    for case_id in case_ids:
        before = [run for run in runs if run.case_id == case_id and run.prompt_variant == "before"]
        after = [run for run in runs if run.case_id == case_id and run.prompt_variant == "after"]
        if not before or len(before) != len(after):
            raise ValueError(f"Unpaired prompt comparison for {case_id}")
        infra = sum(bool(run.error) for run in (*before, *after))
        clean &= infra == 0
        before_pass = sum(run.passed for run in before)
        after_pass = sum(run.passed for run in after)
        all_after_pass &= after_pass == len(after)
        any_correctness_gain |= after_pass > before_pass
        any_correctness_regression |= after_pass < before_pass
        ratio: float | None = None
        if metric and before_pass == len(before) and after_pass == len(after):
            before_costs = [_prompt_cost(run, metric) for run in before]
            after_costs = [_prompt_cost(run, metric) for run in after]
            if all(value is not None for value in (*before_costs, *after_costs)):
                before_total = sum(value for value in before_costs if value is not None)
                after_total = sum(value for value in after_costs if value is not None)
                ratio = after_total / before_total if before_total else None
                any_cost_gain |= ratio is not None and max_ratio is not None and ratio <= max_ratio
            cost_missing |= ratio is None
            cost_regression |= ratio is not None and ratio > 1
        lines.append(
            f"| {case_id} | {before_pass}/{len(before)} | {after_pass}/{len(after)} | {infra} | {ratio:.2f} |"
            if ratio is not None
            else f"| {case_id} | {before_pass}/{len(before)} | {after_pass}/{len(after)} | {infra} | n/a |"
        )
    improved = (
        clean
        and all_after_pass
        and not cost_regression
        and not cost_missing
        and (any_correctness_gain or any_cost_gain)
    )
    if not clean:
        decision = "inconclusive due to infrastructure errors"
    elif any_correctness_regression:
        decision = "regression observed"
    elif cost_regression:
        decision = "cost regression observed"
    elif cost_missing:
        decision = "inconclusive due to missing cost data"
    elif improved:
        decision = "benefit observed"
    else:
        decision = "no measured benefit"
    lines.extend(
        [
            "",
            f"Decision: {decision}.",
            f"Cost target: {metric} after/before <= {max_ratio:.2f}."
            if metric and max_ratio is not None
            else "Cost target: none specified.",
            "Full trajectories and selected prompt-variant hashes are in the before/ and after/ reports.",
        ]
    )
    return "\n".join(lines), improved


def select(
    cases: Sequence[EvalCase],
    ids: Sequence[str],
    categories: Sequence[str],
    tags: Sequence[str] = (),
    *,
    full: bool = False,
) -> list[EvalCase]:
    """Choose the cases to run, keeping dataset order."""
    explicit = bool(ids or categories or tags)
    chosen = [
        case
        for case in cases
        if full
        or (
            (
                case.id in ids
                or any(case.category.endswith(name) for name in categories)
                or bool(set(case.tags) & set(tags))
            )
            if explicit
            else bool(set(case.tags) & DEFAULT_CASE_TAGS)
        )
    ]
    missing = sorted(set(ids) - {case.id for case in chosen})
    if missing:
        raise SystemExit(f"Unknown case ids: {', '.join(missing)}")
    missing_categories = sorted(
        {name for name in categories if not any(case.category.endswith(name) for case in cases)}
    )
    if missing_categories:
        raise SystemExit(f"Unknown categories: {', '.join(missing_categories)}")
    missing_tags = sorted(set(tags) - {tag for case in cases for tag in case.tags})
    if missing_tags:
        raise SystemExit(f"Unknown tags: {', '.join(missing_tags)}")
    if not chosen:
        raise SystemExit("No evaluation cases selected.")
    return chosen


async def run_all(
    cases: Sequence[EvalCase],
    settings: AiSettings,
    provider: Any,
    jobs: int = 1,
    sandbox_factory: SandboxFactory | None = None,
    repetitions: int = 1,
    *,
    prompt_variants: Sequence[tuple[str, str]] | None = None,
    fail_fast: bool = True,
) -> list[CaseRun]:
    """Run selected cases with bounded parallelism and preserve dataset order."""
    if jobs <= 0 or repetitions <= 0:
        raise ValueError("jobs and repetitions must be positive")

    concurrency_limit = asyncio.Semaphore(jobs)
    completed = 0

    variants = tuple(prompt_variants or (("production", SANDBOX_SYSTEM_PROMPT),))
    if len({label for label, _ in variants}) != len(variants):
        raise ValueError("Prompt variant labels must be unique")
    if len(variants) == 1:
        scheduled = [
            (case, repetition, variants[0][0], variants[0][1])
            for case in cases
            for repetition in range(1, repetitions + 1)
        ]
    else:
        scheduled = [
            (case, repetition, label, prompt)
            for repetition in range(1, repetitions + 1)
            for case in cases
            for label, prompt in (variants if repetition % 2 else reversed(variants))
        ]

    async def run_bounded(index: int, case: EvalCase, repetition: int, label: str, prompt: str) -> tuple[int, CaseRun]:
        nonlocal completed
        async with concurrency_limit:
            run = await run_case(provider, settings, case, sandbox_factory, system_prompt=prompt, fail_fast=fail_fast)
            run.repetition = repetition
            run.prompt_variant = label
        completed += 1
        mark = "pass" if run.passed else "FAIL"
        run_label = f"{run.case_id}#{repetition}" if repetitions > 1 else run.case_id
        if len(variants) > 1:
            run_label += f" ({label})"
        print(f"[{completed}/{len(scheduled)}] {mark} {run_label} {run.seconds:.0f}s", flush=True)
        return index, run

    if sandbox_factory is None:
        raise ValueError("sandbox_factory is required for AI evaluation")
    async with managed_sandbox_factory(sandbox_factory):
        indexed_runs = await asyncio.gather(*(run_bounded(index, *item) for index, item in enumerate(scheduled)))
    return [run for _, run in sorted(indexed_runs)]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Require an explicit evaluation scope before any provider work."""
    parser = argparse.ArgumentParser(prog="ai-eval", description="Run the experimental AI evaluation cases.")
    parser.add_argument("--case", action="append", default=[], help="run one case id, repeatable")
    parser.add_argument("--category", action="append", default=[], help="run one category directory, repeatable")
    parser.add_argument("--tag", action="append", default=[], help="run cases with one tag, repeatable")
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="continue after irreversible proposal or tool-limit failures",
    )
    broad_scope = parser.add_mutually_exclusive_group()
    broad_scope.add_argument("--tuning", action="store_true", help="run the default tuning set")
    broad_scope.add_argument("--full", action="store_true", help="run every case")
    prompt_scope = parser.add_mutually_exclusive_group()
    prompt_scope.add_argument("--prompt-step", type=int, help="run with the first N prompt sections (0 is empty)")
    prompt_scope.add_argument("--prompt-compare-step", type=int, help="compare prompt steps N-1 and N")
    prompt_scope.add_argument(
        "--prompt-ablate-step", type=int, help="compare the full prompt without N to the full prompt"
    )
    parser.add_argument("--repeat", type=int, default=None, help="run every selected case this many times")
    parser.add_argument("--cost-metric", choices=("tool-calls", "turns", "uncached-tokens", "seconds"))
    parser.add_argument("--cost-ratio", type=float, help="maximum after/before cost ratio for a cost benefit")
    parser.add_argument("--baseline-report", type=Path, help="compare with a prior report directory or results.jsonl")
    parser.add_argument("--cases-dir", type=Path, default=CASES, help="directory holding the cases")
    parser.add_argument("--output-dir", type=Path, default=None, help="new directory for the report")
    parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_CASE_JOBS,
        help=f"number of cases to run concurrently (default: {DEFAULT_CASE_JOBS})",
    )
    arguments = parser.parse_args(argv)
    comparing = arguments.prompt_compare_step is not None or arguments.prompt_ablate_step is not None
    arguments.repeat = arguments.repeat if arguments.repeat is not None else (3 if comparing else 1)
    if arguments.jobs <= 0 or arguments.repeat <= 0:
        parser.error("--jobs and --repeat must be positive")
    if comparing and not 3 <= arguments.repeat <= 10:
        parser.error("prompt comparisons require --repeat between 3 and 10")
    if (arguments.cost_metric is None) != (arguments.cost_ratio is None):
        parser.error("--cost-metric and --cost-ratio must be supplied together")
    if arguments.cost_ratio is not None and not 0 < arguments.cost_ratio < 1:
        parser.error("--cost-ratio must be between 0 and 1")
    if arguments.cost_ratio is not None and not comparing:
        parser.error("cost targets require a prompt comparison")
    if arguments.baseline_report is not None and comparing:
        parser.error("--baseline-report cannot be combined with a prompt comparison")
    steps = (
        load_prompt_steps()
        if any(
            value is not None
            for value in (arguments.prompt_step, arguments.prompt_compare_step, arguments.prompt_ablate_step)
        )
        else ()
    )
    if arguments.prompt_step is not None and not 0 <= arguments.prompt_step <= len(steps):
        parser.error(f"--prompt-step must be between 0 and {len(steps)}")
    for flag, value in (
        ("--prompt-compare-step", arguments.prompt_compare_step),
        ("--prompt-ablate-step", arguments.prompt_ablate_step),
    ):
        if value is not None and not 1 <= value <= len(steps):
            parser.error(f"{flag} must be between 1 and {len(steps)}")
    if any(not value.strip() for value in arguments.case + arguments.category + arguments.tag):
        parser.error("case, category, and tag selectors must not be empty")
    selected = bool(arguments.case or arguments.category or arguments.tag)
    if selected and (arguments.tuning or arguments.full):
        parser.error("--tuning and --full cannot be combined with case, category, or tag selectors")
    if not selected and not (arguments.tuning or arguments.full or comparing):
        parser.error("choose --case, --category, or --tag, or explicitly pass --tuning or --full")
    return arguments


def _selected_cases(argv: Sequence[str] | None) -> tuple[argparse.Namespace, list[EvalCase]]:
    """Validate the CLI scope and resolve its cases without provider work."""
    arguments = _parse_args(argv)
    step = arguments.prompt_compare_step or arguments.prompt_ablate_step
    default_ids = (
        load_prompt_steps()[step - 1].cases
        if step and not (arguments.case or arguments.category or arguments.tag or arguments.tuning or arguments.full)
        else ()
    )
    if (
        step
        and not default_ids
        and not (arguments.case or arguments.category or arguments.tag or arguments.tuning or arguments.full)
    ):
        raise SystemExit(f"Prompt step {step} has no targeted cases. Add one or select an explicit evaluation scope.")
    # --tuning opts into select's default tagged set when no filters are given.
    cases = select(
        load_cases(arguments.cases_dir),
        [*arguments.case, *default_ids],
        arguments.category,
        arguments.tag,
        full=arguments.full,
    )
    return arguments, cases


def main(argv: Sequence[str] | None = None) -> int:
    """Run the evaluation from the command line."""
    arguments, cases = _selected_cases(argv)
    settings = AiSettings.from_env()
    sandbox_factory = create_sandbox_factory(settings)
    variants = _prompt_variants(arguments)
    started = time.perf_counter()
    runs = asyncio.run(
        run_all(
            cases,
            settings,
            OpenAiCompatibleProvider(settings, include_usage=True, include_attempts=True),
            arguments.jobs,
            sandbox_factory,
            arguments.repeat,
            prompt_variants=variants,
            fail_fast=not arguments.continue_after_failure,
        )
    )
    wall_seconds = time.perf_counter() - started

    output_dir = (arguments.output_dir or default_output_dir()).resolve()
    if len(variants) == 2:
        output_dir.mkdir(parents=True, exist_ok=False)
        for label, prompt in variants:
            write_report(
                [run for run in runs if run.prompt_variant == label],
                output_dir / label,
                jobs=arguments.jobs,
                wall_seconds=wall_seconds,
                metadata=_evaluation_metadata(
                    settings, cases, arguments.repeat, prompt, fail_fast=not arguments.continue_after_failure
                ),
            )
        comparison, improved = prompt_comparison_markdown(runs, arguments.cost_metric, arguments.cost_ratio)
        step_number = arguments.prompt_compare_step or arguments.prompt_ablate_step
        step = load_prompt_steps()[step_number - 1]
        mode = "adjacent steps" if arguments.prompt_compare_step is not None else "full-prompt ablation"
        comparison = f"# Step {step_number}: {step.id}\n\nMode: {mode}. Hypothesis: {step.hypothesis}\n\n" + comparison
        summary = output_dir / "comparison.md"
        summary.write_text(comparison + "\n", encoding="utf-8")
    else:
        summary = write_report(
            runs,
            output_dir,
            jobs=arguments.jobs,
            wall_seconds=wall_seconds,
            metadata=_evaluation_metadata(
                settings, cases, arguments.repeat, variants[0][1], fail_fast=not arguments.continue_after_failure
            ),
            baseline_report=arguments.baseline_report,
        )
        improved = all(run.passed for run in runs)
    print()
    print(summarize(runs))
    print(f"Wall time: {wall_seconds:.1f} seconds with {arguments.jobs} case job(s)")
    print()
    print(f"Evaluation report: {summary}")
    return 0 if improved else 1


def _prompt_variants(arguments: argparse.Namespace) -> tuple[tuple[str, str], ...]:
    """Build only the explicitly requested prompt variants."""
    if arguments.prompt_compare_step is not None:
        step = arguments.prompt_compare_step
        return (("before", prompt_at_step(step - 1)), ("after", prompt_at_step(step)))
    if arguments.prompt_ablate_step is not None:
        step = arguments.prompt_ablate_step
        count = len(load_prompt_steps())
        return (("before", prompt_at_step(count, omit=step)), ("after", prompt_at_step(count)))
    if arguments.prompt_step is not None:
        return ((f"step-{arguments.prompt_step}", prompt_at_step(arguments.prompt_step)),)
    return (("production", SANDBOX_SYSTEM_PROMPT),)


def _evaluation_metadata(
    settings: AiSettings,
    cases: Sequence[EvalCase],
    repetitions: int,
    prompt: str = SANDBOX_SYSTEM_PROMPT,
    *,
    fail_fast: bool = True,
) -> dict[str, Any]:
    """Record enough immutable context to reproduce or compare a run."""
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"], cwd=REPOSITORY_ROOT, check=True, capture_output=True
    ).stdout
    return {
        "git_revision": revision,
        "dirty_diff_sha256": hashlib.sha256(diff).hexdigest() if diff else None,
        "provider_model": settings.provider_model,
        "fail_fast": fail_fast,
        "sandbox_configuration": {
            "backend": settings.sandbox_backend,
            "command_timeout_seconds": settings.sandbox_command_timeout_seconds,
            "control_request_timeout_seconds": settings.sandbox_control_request_timeout_seconds,
            "pause_request_timeout_seconds": settings.sandbox_pause_request_timeout_seconds,
            "max_attempts": settings.sandbox_max_attempts,
        },
        "repetitions": repetitions,
        "case_ids": [case.id for case in cases],
        "cases_sha256": {case.id: case_digest(case) for case in cases},
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "references_sha256": _reference_digests(),
        "fixtures_sha256": {
            fixture: hashlib.sha256(fixture_text(fixture).encode()).hexdigest()
            for fixture in sorted({case.fixture for case in cases})
        },
        "attachments_sha256": {
            attachment.filename: hashlib.sha256(attachment.data).hexdigest()
            for attachment in load_attachment_fixtures(sorted({name for case in cases for name in case.attachments}))
        },
    }


def _reference_digests() -> dict[str, str]:
    """Hash every reference hydrated into the sandbox, not only the schema Markdown.

    The user guide pages and the Taiwan holiday source now steer the agent too, so an
    edit to one of them has to be visible when comparing two runs.
    """
    digests = {
        path.name: hashlib.sha256(str(load_schedule_reference(group)).encode()).hexdigest()
        for group, path in SCHEMA_REFERENCE_FILES.items()
    }
    digests[TAIWAN_HOLIDAYS_SOURCE.name] = hashlib.sha256(load_taiwan_holidays_reference().encode()).hexdigest()
    for relative_path, reference in load_user_guide_references().items():
        digests[f"user-guide/{relative_path}"] = hashlib.sha256(reference.encode()).hexdigest()
    return dict(sorted(digests.items()))


if __name__ == "__main__":
    raise SystemExit(main())
