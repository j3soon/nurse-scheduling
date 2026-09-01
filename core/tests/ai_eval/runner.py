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
import json
import os
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.agent import AgentProposal, AgentReasoning, AgentText, AgentToolUse
from nurse_scheduling.ai.app import build_provider_messages
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ChatStreamEvent,
    OpenAiCompatibleProvider,
    ProviderError,
    TokenUsage,
)
from nurse_scheduling.ai.sandbox import SandboxError, SandboxFactory
from nurse_scheduling.ai.sandbox.factory import create_sandbox_factory
from nurse_scheduling.ai.sandbox_agent import (
    SANDBOX_SYSTEM_PROMPT,
    SandboxAgentLimits,
    SandboxTurnMetrics,
    run_sandbox_agent,
)
from nurse_scheduling.loader import _load_yaml

from .grading import EvalCase, RunOutcome, computed_values, grade, load_cases

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CASES = Path(__file__).resolve().parent / "cases"
FIXTURES = {
    "new-schedule": Path(__file__).resolve().parent / "fixtures" / "new-schedule.yaml",
    "ward87": Path(__file__).resolve().parents[1] / "testcases" / "real",
}
WARD_FILE = "large-ward-with-87-people-2025-11.yaml"


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
    rejected_tools: list[str] = field(default_factory=list)
    llm_inference_seconds: float = 0.0
    llm_turn_seconds: list[float] = field(default_factory=list)
    sandbox_metrics: SandboxTurnMetrics | None = None

    def as_record(self) -> dict[str, Any]:
        """Render one result as a line of the report."""
        return {
            "case_id": self.case_id,
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
            "rejected_tools": self.rejected_tools,
            "failures": self.failures,
            "proposed": self.proposed,
            "reasoning_chars": self.reasoning_chars,
            "answer": self.answer,
            "error": self.error,
            "token_usage": _token_usage_record(self.token_usage, self.token_usage_turns, self.turns),
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

    async def stream_events(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self.turns += 1
        stream = self._provider.stream_events(messages, tools).__aiter__()
        turn_seconds = 0.0
        try:
            while True:
                started = time.monotonic()
                try:
                    event = await anext(stream)
                except StopAsyncIteration:
                    break
                finally:
                    elapsed = time.monotonic() - started
                    self.inference_seconds += elapsed
                    turn_seconds += elapsed
                if isinstance(event, TokenUsage):
                    self.token_usage = event if self.token_usage is None else self.token_usage + event
                    self.token_usage_turns += 1
                    continue
                yield event
        finally:
            self.inference_turn_seconds.append(turn_seconds)
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()


def fixture_text(fixture: str) -> str:
    """Read one of the two starting schedules a case may use."""
    path = FIXTURES[fixture]
    return (path / WARD_FILE if path.is_dir() else path).read_text(encoding="utf-8")


async def run_case(
    provider: Any,
    settings: AiSettings,
    case: EvalCase,
    sandbox_factory: SandboxFactory | None = None,
) -> CaseRun:
    """Answer one case the way the service would, then grade what it produced."""
    text = fixture_text(case.fixture)
    messages = build_provider_messages([], text, case.question, [], [], system_prompt=SANDBOX_SYSTEM_PROMPT)
    counting = _CountingProvider(provider)

    answer: list[str] = []
    tools: list[str] = []
    rejected_tools: list[str] = []
    events: list[dict[str, Any]] = []
    proposal_event: AgentProposal | None = None
    sandbox_metrics = SandboxTurnMetrics()
    reasoning = 0
    started = time.monotonic()
    try:
        if sandbox_factory is None:
            raise ValueError("sandbox_factory is required for AI evaluation")
        agent_events = run_sandbox_agent(
            counting,
            sandbox_factory,
            text,
            messages,
            SandboxAgentLimits.from_settings(settings),
            sandbox_metrics,
        )
        async for event in agent_events:
            if isinstance(event, AgentText):
                answer.append(event.text)
                _record_text(events, "text", event.text)
            elif isinstance(event, AgentReasoning):
                reasoning += len(event.text)
                _record_text(events, "reasoning", event.text)
            elif isinstance(event, AgentToolUse):
                if event.executed:
                    tools.append(event.name if event.ok else f"{event.name}(failed)")
                else:
                    rejected_tools.append(event.name)
                events.append(
                    {
                        "kind": "tool",
                        "name": event.name,
                        "ok": event.ok,
                        "executed": event.executed,
                        "arguments": event.arguments,
                        "result": event.result,
                    }
                )
            elif isinstance(event, AgentProposal):
                proposal_event = event
                events.append({"kind": "proposal", "diff": event.diff})
    except (ProviderError, SandboxError) as error:
        failure = "the provider failed" if isinstance(error, ProviderError) else "the sandbox failed"
        return CaseRun(
            case.id,
            case.category,
            False,
            time.monotonic() - started,
            counting.turns,
            tools,
            [failure],
            "".join(answer),
            False,
            reasoning,
            str(error),
            _trajectory(case, messages, events, None),
            token_usage=counting.token_usage,
            token_usage_turns=counting.token_usage_turns,
            rejected_tools=rejected_tools,
            llm_inference_seconds=counting.inference_seconds,
            llm_turn_seconds=counting.inference_turn_seconds,
            sandbox_metrics=sandbox_metrics,
        )

    elapsed = time.monotonic() - started
    initial = _load_yaml(text.encode("utf-8"))
    proposed = _load_yaml(proposal_event.text.encode("utf-8")) if proposal_event else None
    outcome = RunOutcome(answer="".join(answer), proposed=proposed, initial=initial)
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
        trajectory=_trajectory(case, messages, events, proposal_event, result),
        token_usage=counting.token_usage,
        token_usage_turns=counting.token_usage_turns,
        rejected_tools=rejected_tools,
        llm_inference_seconds=counting.inference_seconds,
        llm_turn_seconds=counting.inference_turn_seconds,
        sandbox_metrics=sandbox_metrics,
    )


def _record_text(events: list[dict[str, Any]], kind: str, text: str) -> None:
    """Join consecutive fragments, so the record reads as what the model wrote."""
    if events and events[-1]["kind"] == kind:
        events[-1]["text"] += text
        return
    events.append({"kind": kind, "text": text})


def _trajectory(
    case: EvalCase,
    messages: Sequence[ChatMessage],
    events: list[dict[str, Any]],
    proposal: Any,
    result: Any = None,
) -> dict[str, Any]:
    """Collect the question, the prompt, and everything the run did."""
    return {
        "fixture": case.fixture,
        "question": case.question,
        "note": case.note,
        "prompt": [dict(message) for message in messages],
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
            f"{'pauses':>8}{'turns':>8}{'tools':>8}"
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
            f"{_median([float(run.turns) for run in group]):>8.1f}"
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
        f"{sum(run.turns for run in runs):>8}"
        f"{sum(len(run.tools) for run in runs):>8}"
    )
    lines.append("Category timing rows are medians. The total row contains sums.")
    failed = [run for run in runs if not run.passed]
    if failed:
        lines.append("")
        lines.append("failures:")
        lines.extend(f"  {run.case_id}: {'; '.join(run.failures) or run.error}" for run in failed)
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
            "| Case | Pauses | Resumes | Total resume wait | Max resume wait |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for run, metrics in sandbox_runs:
        lines.append(
            f"| {run.case_id} | {metrics.pause_count} | {metrics.resume_count} "
            f"| {metrics.resume_wait_seconds:.3f} | {metrics.max_resume_wait_seconds:.3f} |"
        )
    return "\n".join(lines)


def default_output_dir() -> Path:
    """Give each run its own timestamped directory, as the performance benchmark does."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = Path(os.environ.get("AI_EVAL_ARTIFACT_ROOT", REPOSITORY_ROOT / "artifacts"))
    return artifact_root / "ai-evals" / timestamp


def write_report(
    runs: Sequence[CaseRun], output_dir: Path, *, jobs: int = 1, wall_seconds: float | None = None
) -> Path:
    """Write one run's results and summary, and report where the summary landed."""
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "results.jsonl").write_text(
        "".join(json.dumps(run.as_record(), ensure_ascii=False) + "\n" for run in runs), encoding="utf-8"
    )
    # One file per case, so a failure can be read back in full.
    cases_dir = output_dir / "cases"
    cases_dir.mkdir()
    for run in runs:
        (cases_dir / f"{run.case_id}.json").write_text(
            json.dumps(run.as_trajectory(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    summary = output_dir / "summary.md"
    timing = f"\nWall time: {wall_seconds:.1f} seconds\n" if wall_seconds is not None else ""
    summary.write_text(
        f"# AI evaluation\n\nCase concurrency: {jobs}{timing}\n"
        f"## Aggregate\n\n```\n{summarize(runs)}\n```\n\n{sandbox_metrics_markdown(runs)}\n",
        encoding="utf-8",
    )
    return summary


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return 0.0
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def select(cases: Sequence[EvalCase], ids: Sequence[str], categories: Sequence[str]) -> list[EvalCase]:
    """Choose the cases to run, keeping dataset order."""
    chosen = [
        case
        for case in cases
        if (not ids and not categories) or case.id in ids or any(case.category.endswith(name) for name in categories)
    ]
    missing = sorted(set(ids) - {case.id for case in chosen})
    if missing:
        raise SystemExit(f"Unknown case ids: {', '.join(missing)}")
    return chosen


async def run_all(
    cases: Sequence[EvalCase],
    settings: AiSettings,
    provider: Any,
    jobs: int = 1,
    sandbox_factory: SandboxFactory | None = None,
) -> list[CaseRun]:
    """Run selected cases with bounded parallelism and preserve dataset order."""
    if jobs <= 0:
        raise ValueError("jobs must be positive")

    concurrency_limit = asyncio.Semaphore(jobs)
    completed = 0

    async def run_bounded(index: int, case: EvalCase) -> tuple[int, CaseRun]:
        nonlocal completed
        async with concurrency_limit:
            run = await run_case(provider, settings, case, sandbox_factory)
        completed += 1
        mark = "pass" if run.passed else "FAIL"
        print(f"[{completed}/{len(cases)}] {mark} {run.case_id} {run.seconds:.0f}s", flush=True)
        return index, run

    indexed_runs = await asyncio.gather(*(run_bounded(index, case) for index, case in enumerate(cases)))
    return [run for _, run in sorted(indexed_runs)]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the evaluation from the command line."""
    parser = argparse.ArgumentParser(description="Run the experimental AI evaluation cases.")
    parser.add_argument("--case", action="append", default=[], help="run one case id, repeatable")
    parser.add_argument("--category", action="append", default=[], help="run one category directory, repeatable")
    parser.add_argument("--cases-dir", type=Path, default=CASES, help="directory holding the cases")
    parser.add_argument("--output-dir", type=Path, default=None, help="new directory for the report")
    parser.add_argument("--jobs", type=int, default=1, help="number of cases to run concurrently (default: 1)")
    arguments = parser.parse_args(argv)
    if arguments.jobs <= 0:
        parser.error("--jobs must be positive")

    cases = select(load_cases(arguments.cases_dir), arguments.case, arguments.category)
    settings = AiSettings.from_env()
    sandbox_factory = create_sandbox_factory(settings)
    started = time.monotonic()
    runs = asyncio.run(
        run_all(
            cases,
            settings,
            OpenAiCompatibleProvider(settings, include_usage=True),
            arguments.jobs,
            sandbox_factory,
        )
    )
    wall_seconds = time.monotonic() - started

    summary = write_report(
        runs,
        (arguments.output_dir or default_output_dir()).resolve(),
        jobs=arguments.jobs,
        wall_seconds=wall_seconds,
    )
    print()
    print(summarize(runs))
    print(f"Wall time: {wall_seconds:.1f} seconds with {arguments.jobs} case job(s)")
    print()
    print(f"Evaluation report: {summary}")
    return 0 if all(run.passed for run in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
