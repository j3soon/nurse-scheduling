"""On-demand live agent checks with unrestricted production OR-Tools execution."""

# SPDX-License-Identifier: AGPL-3.0-or-later
# This test is mostly AI generated.

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider
from nurse_scheduling.ai.result_context import build_request_audit
from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml
from nurse_scheduling.server.jobs.models import Job, JobFailure, JobRequest, JobState
from nurse_scheduling.server.jobs.runner import OptimizationRunner

from .comparison import _distribution
from .grading import EvalCase
from .runner import RunCheckpoints, _evaluation_metadata, create_sandbox_factory, run_case, write_report


def solve(source: str, output_dir: Path, timeout: int) -> dict:
    """Use the production runner without a forced assignment or synthetic status."""
    validation = validate_frontend_schedule_yaml(source, 2_000_000)
    if not validation.valid:
        raise ValueError("Submitted schedule is outside the frontend subset")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "submitted.yaml").write_text(source, encoding="utf-8")
    job = Job(
        id="real-eval-job",
        state=JobState.RUNNING,
        request=JobRequest("submitted.yaml", "real-eval", "ortools/cp-sat", True, timeout),
        created_at=datetime.now(UTC),
    )
    started = time.perf_counter()
    output = OptimizationRunner().run(job, source.encode(), event_callback=lambda *_: None, should_stop=None)
    solver_and_export_seconds = time.perf_counter() - started
    if isinstance(output, JobFailure) or output.artifact is None:
        raise ValueError(f"Real optimizer produced no workbook: {output}")
    workbook = output.artifact.content
    (output_dir / "result.xlsx").write_bytes(workbook)
    audit = build_request_audit(source, workbook)
    if audit is None:
        raise ValueError("Real optimizer workbook could not be audited")
    metadata = {
        "job_id": job.id,
        "state": "completed",
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "result": {**asdict(output.result), "outcome": output.result.outcome.value},
        "error": None,
        "download_available": True,
        "artifact_error": None,
        "request_audit": audit,
    }
    receipt = {"solver_and_export_seconds": solver_and_export_seconds, "metadata": metadata}
    (output_dir / "solver.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def cases(timeout: int) -> list[EvalCase]:
    question = (
        f"Optimize the current schedule for {timeout} seconds using its existing preferences. "
        "When the result arrives, return a JSON object with solverStatus (the exact solver status), "
        "score (the numeric objective), and strongUnmet (the number of expanded person/date "
        "shift requests with weight 11000000000 that are unmet)."
    )
    return [
        EvalCase(
            id=f"real-optimizer-{fixture}",
            fixture=fixture,
            question=question,
            user_turns=(question,),
            expect_proposal=False,
            semantic_check="optimizer-start-source",
            optimizer_completion="real",
            category="real-optimizer",
        )
        for fixture in ("policy-audit", "ward87")
    ]


async def benchmark(settings: AiSettings, root: Path, repeat: int, timeout: int) -> bool:
    selected = cases(timeout)
    metadata = _evaluation_metadata(settings, [replace(case, optimizer_completion="") for case in selected], repeat)
    metadata["cases_sha256"] = {
        case.id: hashlib.sha256(json.dumps(asdict(case), sort_keys=True).encode()).hexdigest() for case in selected
    }
    metadata["execution"] = {
        "optimizer": "production OptimizationRunner, unrestricted ortools/cp-sat",
        "timeout_seconds": timeout,
        "transport": "local subprocess, simulated start acknowledgement, real completion callback",
        "jobs": 4,
    }
    checkpoints = RunCheckpoints(root, {"production": metadata}, repeat, repeat * len(selected))
    provider = OpenAiCompatibleProvider(settings, include_usage=True, include_attempts=True)
    factory = create_sandbox_factory(settings)
    semaphore = asyncio.Semaphore(4)
    observations = []

    async def one(original: EvalCase, repetition: int):
        async with semaphore:
            case = replace(original, answer_json={})
            directory = root / f"{case.id}-{repetition}"
            directory.mkdir(parents=True, exist_ok=True)
            receipt = {}

            def completion(_name: str, source: str):
                # A separate process isolates solver resource use and stdout from concurrent agents.
                boundary_started = time.perf_counter()
                (directory / "submitted.yaml").write_text(source, encoding="utf-8")
                with (directory / "solver.log").open("w", encoding="utf-8") as log:
                    subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "tests.ai_eval.real_optimizer",
                            "--solve",
                            str(directory),
                            "--timeout",
                            str(timeout),
                        ],
                        check=True,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=timeout + 180,
                    )
                receipt.update(json.loads((directory / "solver.json").read_text(encoding="utf-8")))
                receipt["optimizer_boundary_seconds"] = time.perf_counter() - boundary_started
                result = receipt["metadata"]
                strong_unmet = sum(
                    row["unmet"] for row in result["request_audit"]["summary"] if row["weight"] == 11_000_000_000
                )
                case.answer_json.update(
                    solverStatus=result["result"]["solver_status"],
                    score=result["result"]["score"],
                    strongUnmet=strong_unmet,
                )
                return (directory / "result.xlsx").read_bytes(), result

            try:
                run = await run_case(provider, settings, case, factory, optimizer_completion_factory=completion)
            except (subprocess.SubprocessError, OSError, ValueError) as error:
                # Preserve completed attempts and fail the batch rather than hiding a solver failure.
                (directory / "error.txt").write_text(str(error) + "\n", encoding="utf-8")
                raise
            run.repetition = repetition
            if not receipt:
                run.passed = False
                run.failures.append("Real optimizer did not execute")
            solver_seconds = receipt.get("solver_and_export_seconds")
            boundary_seconds = receipt.get("optimizer_boundary_seconds")
            observations.append(
                {
                    "case_id": case.id,
                    "repetition": repetition,
                    "passed": run.passed,
                    "solver_and_export_seconds": solver_seconds,
                    "optimizer_boundary_seconds": boundary_seconds,
                    "agent_and_sandbox_seconds": run.seconds - boundary_seconds
                    if boundary_seconds is not None
                    else None,
                    "answer_expected": case.answer_json,
                    "audit": receipt.get("metadata", {}).get("request_audit"),
                }
            )
            checkpoints.record(run)
            print(f"{case.id} #{repetition}: {'PASS' if run.passed else 'FAIL'} {run.seconds:.1f}s", flush=True)
            return run

    started = time.perf_counter()
    from nurse_scheduling.ai.sandbox import managed_sandbox_factory

    try:
        async with managed_sandbox_factory(factory):
            runs = await asyncio.gather(*(one(case, n) for n in range(1, repeat + 1) for case in selected))
    except BaseException:
        checkpoints.set_status("interrupted")
        raise
    write_report(runs, root, jobs=4, wall_seconds=time.perf_counter() - started, metadata=metadata, checkpointed=True)
    summary = {
        "attempts": observations,
        "timing": {
            case.id: {
                key: _distribution(
                    [row[key] for row in observations if row["case_id"] == case.id and row[key] is not None]
                )
                for key in ("solver_and_export_seconds", "optimizer_boundary_seconds", "agent_and_sandbox_seconds")
            }
            for case in selected
        },
        "limitations": "Local engine/export/callback check. HTTP, queue, anonymization, and worker recovery are not exercised. Optimizer boundary includes subprocess startup and audits. Solver/export time includes model construction.",
    }
    (root / "real-optimizer.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    checkpoints.set_status("complete")
    return all(run.passed for run in runs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--solve", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeat < 1 or args.timeout < 1:
        parser.error("repeat and timeout must be positive")
    if args.solve:
        solve((args.solve / "submitted.yaml").read_text(encoding="utf-8"), args.solve, args.timeout)
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required")
    root = args.output_dir.resolve()
    repository_artifacts = Path(__file__).resolve().parents[3] / "artifacts"
    if not root.is_relative_to(repository_artifacts):
        parser.error("--output-dir must be under repository-root artifacts/")
    return 0 if asyncio.run(benchmark(AiSettings.from_env(), root, args.repeat, args.timeout)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
