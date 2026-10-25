"""Run human-reviewed AI testcases through production workspace APIs."""

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
import mimetypes
import os
import shlex
from contextlib import aclosing
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.agent import Agent
from nurse_scheduling.ai.agent_types import AgentMessageEnd, AgentProposal, AgentToolStart, AgentToolUse
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.context import (
    SCHEDULE_CHANGED_EVENT,
    build_provider_messages,
    cap_transcript,
    project_history,
    retained_entries,
    upload_event,
)
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider
from nurse_scheduling.ai.sandbox import SandboxError, SandboxFactory, managed_sandbox_factory
from nurse_scheduling.ai.sandbox.factory import create_sandbox_factory
from nurse_scheduling.ai.transcript import AppEventEntry, UserMessage
from nurse_scheduling.ai.workspace import AgentAnalysis, SandboxAttachment, WorkspaceLimits
from nurse_scheduling.ai.workspace_tools import run_workspace

from .assertions import check_event, check_schedule
from .judge import evaluate
from .reporting import print_attempt, print_summary
from .schema import FIXTURES, TESTCASES, Case, DefinitionError, Step, load_case


class DatedFactory:
    """Set only the disposable sandbox's clock, before workspace hydration."""

    def __init__(self, factory: SandboxFactory) -> None:
        self.factory = factory
        self.date: datetime | None = None

    async def create(self, *, envs: dict[str, str] | None = None):
        sandbox = await self.factory.create(envs=envs)
        if self.date is None:
            return sandbox
        try:
            instant = self.date.timestamp()
            result = await sandbox.run(
                f"sudo -n date --set={shlex.quote('@' + str(instant))} +%s && date +%s", timeout_seconds=10
            )
            readings = [float(line) for line in result.stdout.splitlines()]
            if result.exit_code != 0 or len(readings) != 2 or any(abs(reading - instant) > 10 for reading in readings):
                raise SandboxError("could not set and verify the E2B sandbox clock")
        except BaseException:
            await sandbox.close()
            raise
        return sandbox


def _timezone(date: datetime | None) -> str:
    if date is None:
        return "UTC"
    # POSIX TZ signs are the inverse of ISO 8601 offsets.
    seconds = int(date.utcoffset().total_seconds())
    sign = "-" if seconds >= 0 else "+"
    hours, remainder = divmod(abs(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"


async def run_case(
    case: Case,
    provider: Any,
    settings: AiSettings,
    factory: SandboxFactory,
    *,
    judge_provider: Any = None,
) -> bool:
    """Execute one isolated conversation and retain all assertions and messages."""
    schedule = (FIXTURES / "empty.yaml").read_text(encoding="utf-8")
    history = []
    attachments = []
    analysis = None
    clock = DatedFactory(factory)
    events = []
    checks: list[Step] = []
    trace = []
    before = schedule
    turn = cursor = number = turn_step = 0
    pending = False
    errors = []

    def assert_schedule():
        try:
            check_schedule(checks, before, schedule)
        except AssertionError as error:
            errors.append({"turn": turn, "step": number, "kind": "assertion", "error": str(error)})

    try:
        for step in case.steps:
            if step.kind in {"date", "yaml", "user"} and pending:
                number = checks[-1].number if checks else turn_step
                assert_schedule()
                pending = False
            number = step.number
            if step.kind == "date":
                clock.date = step.value
            elif step.kind == "yaml":
                schedule = step.value.read_text(encoding="utf-8")
                analysis = None
                if history:
                    history.append(AppEventEntry(SCHEDULE_CHANGED_EVENT))
            elif step.kind == "user":
                turn += 1
                turn_step = step.number
                cursor = 0
                checks, events = [], []
                before = schedule
                uploaded = [
                    SandboxAttachment(
                        path.name, mimetypes.guess_type(path.name)[0] or "application/octet-stream", path.read_bytes()
                    )
                    for path in step.options.get("attachment", ())
                ]
                if uploaded:
                    history.append(AppEventEntry(upload_event(uploaded, first_index=len(attachments) + 1)))
                    attachments.extend(uploaded)
                    analysis = None
                messages = build_provider_messages(
                    project_history(history, settings.max_history_chars),
                    schedule,
                    step.value,
                    max_download_bytes=settings.max_download_bytes,
                )
                agent = Agent()
                entry = {
                    "turn": turn,
                    "user": step.value,
                    "before": before,
                    "events": events,
                    "after": schedule,
                    "attachments": [
                        {"name": item.filename, "media_type": item.media_type, "bytes": len(item.data)}
                        for item in uploaded
                    ],
                }
                trace.append(entry)
                stream = run_workspace(
                    provider,
                    clock,
                    schedule,
                    messages,
                    WorkspaceLimits.from_settings(settings),
                    agent=agent,
                    attachments=attachments,
                    analysis=analysis,
                    timezone=_timezone(clock.date),
                )
                async with aclosing(stream):
                    async for event in stream:
                        if isinstance(event, AgentMessageEnd):
                            events.append({"kind": "assistant", **asdict(event.message)})
                            if event.message.stop_reason in {"error", "aborted", "length"}:
                                raise RuntimeError(f"assistant response ended with {event.message.stop_reason}")
                        elif isinstance(event, AgentToolStart):
                            events.append(
                                {
                                    "kind": "tool",
                                    "name": event.name,
                                    "arguments": json.loads(event.arguments),
                                    "id": event.tool_call_id,
                                }
                            )
                        elif isinstance(event, AgentToolUse):
                            events.append(
                                {
                                    "kind": "tool_result",
                                    "name": event.name,
                                    "ok": event.ok,
                                    "text": event.result,
                                    "id": event.tool_call_id,
                                    "details": event.details,
                                }
                            )
                        elif isinstance(event, AgentProposal):
                            schedule = event.text
                            entry["after"] = schedule
                        elif isinstance(event, AgentAnalysis):
                            analysis = event
                completed = retained_entries([UserMessage(step.value), *agent.state.messages])
                history.extend(completed)
                cap_transcript(history, settings.max_history_messages, settings.max_history_chars, len(completed))
                pending = True
            elif step.kind == "schedule":
                checks.append(step)
            else:
                try:
                    cursor = check_event(step, events, cursor)
                except AssertionError as error:
                    errors.append({"turn": turn, "step": number, "kind": "assertion", "error": str(error)})
        if pending:
            number = checks[-1].number if checks else turn_step
            assert_schedule()
    except Exception as error:  # noqa: BLE001 - Preserve evidence from provider and sandbox adapters.
        errors.append({"turn": turn, "step": number, "kind": "execution", "error": str(error)})
    judge_turn = 0
    for step in case.steps:
        if step.kind == "user":
            judge_turn += 1
        elif step.kind == "assistant" and "judge" in step.value and judge_turn <= len(trace):
            judge = judge_provider if judge_provider is not None else provider
            model = getattr(getattr(judge, "identity", None), "model", settings.provider_model)
            verdict = await evaluate(judge, step.value["judge"], trace[:judge_turn], model)
            trace[judge_turn - 1]["events"].append({**verdict, "step": step.number})
            if not verdict["passed"]:
                errors.append(
                    {
                        "turn": judge_turn,
                        "step": step.number,
                        "kind": "judge",
                        "error": verdict["error"] or verdict["reason"],
                    }
                )
    print_attempt(case, errors, trace, settings)
    return not errors


async def run_cases(cases, provider, settings, factory, diagnostic_attempts: int = 1, *, judge_provider=None) -> bool:
    """Repeat initially failed cases for inspection without changing their outcome."""
    results = []
    for case in cases:
        for attempt in range(1, diagnostic_attempts + 1):
            print(f"Attempt {attempt}: {case.path}", flush=True)
            passed = await run_case(case, provider, settings, factory, judge_provider=judge_provider)
            results.append(
                {
                    "case": case.path.stem,
                    "attempt": attempt,
                    "passed": passed,
                }
            )
            if attempt == 1 and passed:
                break
    print_summary(results)
    return all(result["passed"] for result in results)


async def _run(cases: list[Case], diagnostic_attempts: int) -> bool:
    settings = AiSettings.from_env()
    provider = OpenAiCompatibleProvider(settings)
    factory = create_sandbox_factory(settings)
    judge_model = os.getenv("AI_TEST_JUDGE_MODEL", "").strip() or settings.provider_model
    judge_provider = OpenAiCompatibleProvider(
        replace(settings, provider_model=judge_model), parameters={"temperature": 0}
    )
    async with managed_sandbox_factory(factory):
        return await run_cases(cases, provider, settings, factory, diagnostic_attempts, judge_provider=judge_provider)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument("paths", nargs="*", type=Path, help="testcase files or directories (default: all cases)")
    parser.add_argument(
        "--diagnostic-attempts",
        type=int,
        choices=range(1, 4),
        default=1,
        help="total attempts for initially failed cases, without clearing failure (default: 1)",
    )
    args = parser.parse_args(argv)
    try:
        paths = set()
        for path in args.paths or [TESTCASES]:
            paths.update(path.rglob("*.yaml") if path.is_dir() else [path])
        if not paths:
            raise DefinitionError("no testcase YAML files found")
        cases = [load_case(path) for path in sorted(paths)]
        print(f"Validated {len(cases)} testcase(s).", flush=True)
        return 0 if args.command == "validate" or asyncio.run(_run(cases, args.diagnostic_attempts)) else 1
    except (DefinitionError, ValueError, OSError) as error:
        print(f"ERROR: {error}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
