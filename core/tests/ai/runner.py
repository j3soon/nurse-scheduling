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
import hashlib
import json
import mimetypes
import shlex
from contextlib import aclosing
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
from .schema import FIXTURES, ROOT, TESTCASES, Case, DefinitionError, Step, load_case


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


def _failure(
    case: Case, turn: int, step: int, error: Exception, trace: list[dict], output: Path, settings: AiSettings
) -> None:
    record = {"case": str(case.path), "turn": turn, "step": step, "error": str(error), "turns": trace}
    text = json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n"
    for secret in (settings.provider_api_key, settings.e2b_api_key):
        if secret:
            text = text.replace(secret, "[redacted]")
    output.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256(str(case.path).encode()).hexdigest()[:8]
    path = output / f"{case.path.stem}-{suffix}.json"
    path.write_text(text, encoding="utf-8")
    summary = json.loads(text)["error"]
    print(f"FAIL {case.path}: turn {turn}, step {step}: {summary}\nEvidence: {path}", flush=True)


async def run_case(case: Case, provider: Any, settings: AiSettings, factory: SandboxFactory, output: Path) -> bool:
    """Execute one isolated conversation and stop at its first failed assertion."""
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
    try:
        for step in case.steps:
            if step.kind in {"date", "yaml", "user"} and pending:
                number = checks[-1].number if checks else turn_step
                check_schedule(checks, before, schedule)
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
                entry = {"turn": turn, "user": step.value, "before": before, "events": events, "after": schedule}
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
                            if event.message.stop_reason in {"error", "aborted", "length"}:
                                raise RuntimeError(f"assistant response ended with {event.message.stop_reason}")
                            if event.message.text:
                                events.append({"kind": "assistant", "text": event.message.text})
                        elif isinstance(event, AgentToolStart):
                            events.append(
                                {"kind": "tool", "name": event.name, "arguments": json.loads(event.arguments)}
                            )
                        elif isinstance(event, AgentToolUse):
                            events.append(
                                {"kind": "tool_result", "name": event.name, "ok": event.ok, "text": event.result}
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
                cursor = check_event(step, events, cursor)
        if pending:
            number = checks[-1].number if checks else turn_step
            check_schedule(checks, before, schedule)
    except Exception as error:  # noqa: BLE001 - Preserve evidence from provider and sandbox adapters.
        _failure(case, turn, number, error, trace, output, settings)
        return False
    print(f"PASS {case.path} ({turn} turns)", flush=True)
    return True


async def _run(cases: list[Case], output: Path) -> bool:
    settings = AiSettings.from_env()
    provider = OpenAiCompatibleProvider(settings)
    factory = create_sandbox_factory(settings)
    passed = True
    async with managed_sandbox_factory(factory):
        for case in cases:
            passed = await run_case(case, provider, settings, factory, output) and passed
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument("paths", nargs="*", type=Path, help="testcase files or directories (default: all cases)")
    parser.add_argument("--output-dir", type=Path, default=ROOT.parents[2] / "artifacts" / "ai-testcases")
    args = parser.parse_args(argv)
    try:
        paths = set()
        for path in args.paths or [TESTCASES]:
            paths.update(path.rglob("*.yaml") if path.is_dir() else [path])
        if not paths:
            raise DefinitionError("no testcase YAML files found")
        cases = [load_case(path) for path in sorted(paths)]
        print(f"Validated {len(cases)} testcase(s).", flush=True)
        return 0 if args.command == "validate" or asyncio.run(_run(cases, args.output_dir)) else 1
    except (DefinitionError, ValueError, OSError) as error:
        print(f"ERROR: {error}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
