"""Compare live agent recovery with a historical E2B timeout backend."""

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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

# This test is mostly AI generated.

import argparse
import asyncio
import hashlib
import importlib.util
import json
import statistics
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider
from nurse_scheduling.ai.sandbox import SandboxError, SandboxFileNotFoundError, managed_sandbox_factory
from nurse_scheduling.ai.sandbox.e2b import E2BSandboxFactory
from nurse_scheduling.ai.workspace import SANDBOX_SYSTEM_PROMPT

from .comparison import METRICS, _distribution, _metric
from .grading import load_cases
from .runner import CASES, RunCheckpoints, fixture_text, run_case, write_report

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CASE_ID = "tool-timeout-checkpoint-recovery"
BACKEND_PATH = "core/nurse_scheduling/ai/sandbox/e2b.py"


class ObservedSandbox:
    """Observe real operations and audit the workspace before managed teardown."""

    def __init__(self, backend):
        self.backend = backend
        self.initial_id = backend.sandbox_id
        self.commands = []
        self.hydrations = 0
        self.timeout_ended = None
        self.observations = {}

    def __getattr__(self, name):
        return getattr(self.backend, name)

    async def write_files(self, files):
        self.hydrations += 1
        return await self.backend.write_files(files)

    async def run(self, command, *, timeout_seconds=None):
        result = await self.backend.run(command, timeout_seconds=timeout_seconds)
        self.commands.append(
            {
                "command": command,
                "timeout_seconds": timeout_seconds,
                "timed_out": result.timed_out,
                "terminal": result.sandbox_terminated,
            }
        )
        if result.timed_out:
            self.timeout_ended = time.perf_counter()
        return result

    async def close(self):
        self.observations.update(
            sandbox_id=self.initial_id,
            same_sandbox=self.backend.sandbox_id == self.initial_id,
            hydration_count=self.hydrations,
            commands=self.commands,
            checkpoint_preserved=False,
            executed_once=False,
            no_delayed_write=False,
            verification_errors=[],
        )
        try:
            if self.timeout_ended is not None and self.backend.lifecycle_state.value != "closed":
                self.observations["recovery_seconds"] = time.perf_counter() - self.timeout_ended
                async with self.backend.activity_batch():
                    # Wait past the descendant's write deadline even if the LLM responds quickly.
                    await asyncio.sleep(max(0, self.timeout_ended + 4.2 - time.perf_counter()))
                    checkpoint = json.loads(await self.backend.read_file("/workspace/timeout-checkpoint.json"))
                    source_hash = hashlib.sha256(fixture_text("small-clinic").encode()).hexdigest()
                    self.observations["checkpoint_preserved"] = checkpoint == {
                        "description": "Recovered clinic checkpoint",
                        "source_sha256": source_hash,
                    }
                    self.observations["executed_once"] = (
                        await self.backend.read_file("/workspace/timeout-attempts.txt") == b"once\n"
                    )
                    try:
                        await self.backend.read_file("/workspace/late-write.txt")
                    except SandboxFileNotFoundError:
                        self.observations["no_delayed_write"] = True
        except (SandboxError, ValueError, TypeError) as error:
            self.observations["verification_errors"].append(f"{type(error).__name__}: {error}")
        finally:
            await self.backend.close()


class ObservedFactory:
    def __init__(self, factory):
        self.factory = factory
        self.created = []

    async def create(self):
        sandbox = ObservedSandbox(await self.factory.create())
        self.created.append(sandbox)
        return sandbox


def recovery_failures(created):
    """Independent runtime oracle, in addition to the ordinary semantic grader."""
    if len(created) != 1:
        return ["Recovery must use exactly one sandbox."]
    observed = created[0].observations
    errors = list(observed.get("verification_errors", []))
    for key in ("same_sandbox", "checkpoint_preserved", "executed_once", "no_delayed_write"):
        if not observed.get(key):
            errors.append(f"Runtime invariant failed: {key}")
    if observed.get("hydration_count") != 1:
        errors.append("Recovery must not hydrate the sandbox again.")
    timeouts = [command for command in observed.get("commands", []) if command["timed_out"]]
    if len(timeouts) != 1 or timeouts[0]["terminal"]:
        errors.append("Expected exactly one recoverable command timeout.")
    return errors


def historical_factory(revision, settings, output_dir):
    """Load only the historical adapter, keeping prompt, tools, and grading fixed."""
    source = subprocess.check_output(["git", "show", f"{revision}:{BACKEND_PATH}"], cwd=REPOSITORY_ROOT, text=True)
    path = output_dir / "baseline-e2b.py"
    path.write_text(source, encoding="utf-8")
    name = "nurse_scheduling.ai.sandbox._timeout_baseline"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.E2BSandboxFactory.from_settings(settings), hashlib.sha256(source.encode()).hexdigest()


async def benchmark(settings, baseline_ref, output_dir, repeat=3, jobs=4):
    case = next(case for case in load_cases(CASES) if case.id == CASE_ID)
    revision = (
        await asyncio.to_thread(
            subprocess.check_output,
            ["git", "rev-parse", "--verify", f"{baseline_ref}^{{commit}}"],
            cwd=REPOSITORY_ROOT,
            text=True,
        )
    ).strip()
    before, source_hash = await asyncio.to_thread(historical_factory, revision, settings, output_dir)
    factories = {"before": before, "after": E2BSandboxFactory.from_settings(settings)}
    metadata = {
        "baseline_revision": revision,
        "baseline_backend_sha256": source_hash,
        "current_backend_sha256": hashlib.sha256((REPOSITORY_ROOT / BACKEND_PATH).read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(SANDBOX_SYSTEM_PROMPT.encode()).hexdigest(),
        "case_sha256": hashlib.sha256((CASES / "basics/00-tools" / f"{CASE_ID}.json").read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(fixture_text(case.fixture).encode()).hexdigest(),
        "attachment_sha256": hashlib.sha256(
            (Path(__file__).with_name("fixtures") / "timeout-checkpoint.txt").read_bytes()
        ).hexdigest(),
        "model": settings.provider_model,
        "repeat": repeat,
        "jobs": jobs,
        "scope": "Only the E2B adapter differs. No automatic retry of the baseline's aborted turn.",
    }
    checkpoints = {arm: RunCheckpoints(output_dir / arm, {arm: metadata}, repeat, repeat) for arm in factories}
    provider = OpenAiCompatibleProvider(settings, include_usage=True, include_attempts=True)
    semaphore = asyncio.Semaphore(jobs)

    async def exercise(arm, repetition):
        async with semaphore:
            factory = ObservedFactory(factories[arm])
            run = await run_case(provider, settings, case, factory, fail_fast=False)
            run.repetition = repetition
            run.prompt_variant = arm
            if arm == "after":
                run.failures.extend(recovery_failures(factory.created))
                run.passed = run.passed and not run.failures
            observations = [sandbox.observations for sandbox in factory.created]
            (output_dir / f"{arm}-{repetition}-runtime.json").write_text(
                json.dumps({"creations": len(factory.created), "sandboxes": observations}, indent=2) + "\n"
            )
            checkpoints[arm].record(run)
            print(f"{arm} #{repetition}: {'PASS' if run.passed else 'FAIL'} ({run.seconds:.1f}s)", flush=True)
            return arm, run

    async with managed_sandbox_factory(before), managed_sandbox_factory(factories["after"]):
        ordered = [
            (arm, repetition)
            for repetition in range(1, repeat + 1)
            for arm in (("before", "after") if repetition % 2 else ("after", "before"))
        ]
        tasks = [asyncio.create_task(exercise(*item)) for item in ordered]
        try:
            completed = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for checkpoint in checkpoints.values():
                checkpoint.set_status("interrupted")
            raise
    runs = {
        arm: sorted((run for label, run in completed if label == arm), key=lambda run: run.repetition)
        for arm in factories
    }
    for arm in factories:
        write_report(
            runs[arm],
            output_dir / arm,
            jobs=jobs,
            metadata=metadata,
            checkpointed=True,
            baseline_report=output_dir / "before/results.jsonl" if arm == "after" else None,
        )
        checkpoints[arm].set_status("complete")
    attempt_metrics = {}
    for arm, group in runs.items():
        records = [run.as_record() for run in group]
        attempt_metrics[arm] = {}
        for name in METRICS:
            values = [value for record in records if (value := _metric(record, name)) is not None]
            attempt_metrics[arm][name] = {"available_runs": len(values), **_distribution(values)}
    (output_dir / "attempt-metrics.json").write_text(json.dumps(attempt_metrics, indent=2) + "\n")
    lines = [
        "# Live agent timeout recovery",
        "",
        "The historical arm aborts the turn. Costs below describe all attempts, not equivalent successful work.",
        "Matched passing token deltas and SD are available in after/summary.md only if both arms succeed.",
        "No automatic sandbox recreation existed in the baseline, so avoided rehydration time is not measured.",
        "",
        "| Arm | Passes | Infrastructure errors | Mean seconds | Mean tool calls | Mean turns | Mean total tokens |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm, group in runs.items():
        tokens = [
            run.token_usage.total_tokens for run in group if run.token_usage and run.token_usage_turns == run.turns
        ]
        token_mean = f"{statistics.mean(tokens):.0f}" if len(tokens) == len(group) else "unavailable"
        lines.append(
            f"| {arm} | {sum(run.passed for run in group)}/{repeat} | {sum(bool(run.error) for run in group)} "
            f"| {statistics.mean(run.seconds for run in group):.1f} "
            f"| {statistics.mean(len(run.tools) for run in group):.1f} "
            f"| {statistics.mean(run.turns for run in group):.1f} | {token_mean} |"
        )
    lines.extend(
        [
            "",
            "## All-attempt metrics",
            "",
            "Means and sample SD include failed attempts. They are descriptive, not cost improvement evidence.",
            "",
            "| Metric | Before mean ± SD (n) | After mean ± SD (n) |",
            "| --- | ---: | ---: |",
        ]
    )
    for name in METRICS:
        cells = []
        for arm in factories:
            stat = attempt_metrics[arm][name]
            cells.append(
                f"{stat['mean']:.1f} ± {stat['std']:.1f} ({stat['available_runs']})"
                if stat["std"] is not None
                else "unavailable"
            )
        lines.append(f"| {name} | {' | '.join(cells)} |")
    lines.extend(
        [
            "",
            "## Runtime observations",
            "",
            "| Arm | Creations per run | Hydrations per run | Verified recovery | Mean recovery seconds ± SD |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for arm in factories:
        runtime = [json.loads((output_dir / f"{arm}-{rep}-runtime.json").read_text()) for rep in range(1, repeat + 1)]
        creations = [item["creations"] for item in runtime]
        hydrations = [sum(sandbox.get("hydration_count", 0) for sandbox in item["sandboxes"]) for item in runtime]
        verified = [
            sandbox
            for item in runtime
            for sandbox in item["sandboxes"]
            if all(
                sandbox.get(key)
                for key in ("same_sandbox", "checkpoint_preserved", "executed_once", "no_delayed_write")
            )
        ]
        recovery = [sandbox["recovery_seconds"] for sandbox in verified if "recovery_seconds" in sandbox]
        stat = _distribution(recovery)
        timing = f"{stat['mean']:.2f} ± {stat['std']:.2f}" if stat["std"] is not None else "unavailable"
        lines.append(
            f"| {arm} | {statistics.mean(creations):.1f} | {statistics.mean(hydrations):.1f} | {len(verified)}/{repeat} | {timing} |"
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n")
    return all(run.passed for run in runs["after"]) and not any(run.error for group in runs.values() for run in group)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True, help="trusted local revision with teardown on timeout")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--output-dir", type=Path)
    arguments = parser.parse_args()
    if arguments.repeat <= 0 or arguments.jobs <= 0:
        parser.error("repeat and jobs must be positive")
    settings = replace(AiSettings.from_env(), sandbox_backend="e2b", sandbox_turn_timeout_seconds=300)
    if not settings.e2b_api_key:
        parser.error("E2B_API_KEY is required")
    output = arguments.output_dir or REPOSITORY_ROOT / "artifacts/ai-timeout-recovery" / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    output.mkdir(parents=True, exist_ok=False)
    success = asyncio.run(benchmark(settings, arguments.baseline_ref, output, arguments.repeat, arguments.jobs))
    print(f"Report: {output / 'summary.md'}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
