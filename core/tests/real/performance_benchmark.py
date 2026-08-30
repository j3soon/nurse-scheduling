"""Benchmark OR-Tools CP-SAT on the opt-in real-world scenario."""

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
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nurse_scheduling
from nurse_scheduling.solver_interface import (
    SchedulePhaseProgress,
    SolverProgress,
    serialize_schedule_phase_progress,
    serialize_solver_progress,
)

from .assignment_fixture import serialize_assignment_fixture
from .schedule_real_helper import REAL_TESTCASE

COMPUTE_MODE = "compute"
SEARCH_MODE = "search"
DEFAULT_COMPUTE_RUNS = 5
DEFAULT_COMPUTE_TIMEOUT_SECONDS = 900
DEFAULT_WARMUP_RUNS = 1
DEFAULT_SEARCH_RUNS = 3
DEFAULT_SEARCH_TIMEOUT_SECONDS = 300
ATTAINMENT_THRESHOLDS = (
    0,
    1_000_000_000_000,
    2_000_000_000_000,
    3_000_000_000_000,
    4_000_000_000_000,
    4_200_000_000_000,
    4_300_000_000_000,
    4_400_000_000_000,
    4_450_000_000_000,
    4_470_000_000_000,
)
PERFORMANCE_REFERENCE_TIME_SECONDS = 100
SOLVER = "ortools/cp-sat"
REPOSITORY_ROOT = Path(__file__).parents[3]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _default_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = Path(os.environ.get("BENCHMARK_ARTIFACT_ROOT", REPOSITORY_ROOT / "artifacts"))
    return artifact_root / "performance-benchmarks" / timestamp


def _app_version() -> str:
    environment_version = os.environ.get("BENCHMARK_APP_VERSION")
    if environment_version:
        return environment_version
    version_file = REPOSITORY_ROOT / ".app-version"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPOSITORY_ROOT), "describe", "--tags", "--always", "--dirty"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "v0.0.0-unknown"


def _read_first_matching_line(path: Path, prefix: str) -> str | None:
    try:
        with path.open(encoding="utf-8") as input_file:
            for line in input_file:
                if line.startswith(prefix):
                    return line.partition(":")[2].strip()
    except OSError:
        return None
    return None


def _environment_metadata() -> dict[str, Any]:
    affinity = None
    if hasattr(os, "sched_getaffinity"):
        affinity = sorted(os.sched_getaffinity(0))
    load_average = None
    try:
        load_average = list(os.getloadavg())
    except OSError:
        pass
    return {
        "appVersion": _app_version(),
        "benchmarkSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "coreSourceSha256": _source_tree_sha256(REPOSITORY_ROOT / "core" / "nurse_scheduling"),
        "ortoolsVersion": importlib.metadata.version("ortools"),
        "pythonVersion": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpuModel": _read_first_matching_line(Path("/proc/cpuinfo"), "model name"),
        "logicalCpuCount": os.cpu_count(),
        "cpuAffinity": affinity,
        "loadAverageAtStart": load_average,
        "memoryTotalKiB": _memory_total_kib(),
    }


def _source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _memory_total_kib() -> int | None:
    value = _read_first_matching_line(Path("/proc/meminfo"), "MemTotal")
    if value is None:
        return None
    try:
        return int(value.split()[0])
    except (ValueError, IndexError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _claimed_performance_env(report: dict[str, Any]) -> str | None:
    """Build deployable environment settings from a complete compute benchmark."""
    config = report["config"]
    summary = report["summary"]
    score = summary.get("performanceScore")
    if config["mode"] != COMPUTE_MODE or score is None or summary["completedRuns"] != summary["requestedRuns"]:
        return None
    return "\n".join(
        (
            f"CLAIMED_PERFORMANCE_SCORE={score}",
            f"CLAIMED_PERFORMANCE_APP_VERSION={report['environment']['appVersion']}",
            f"CLAIMED_PERFORMANCE_MEASURED_AT={report['createdAt']}",
            "",
        )
    )


def _write_schedule_artifacts(run_dir: Path, file_content: bytes, result: Any) -> dict[str, str]:
    if result.dataframe is None or result.solution is None or result.score is None:
        return {}
    schedule_filename = "schedule.csv"
    assignment_filename = "assignment.json"
    result.dataframe.to_csv(
        run_dir / schedule_filename,
        index=False,
        header=False,
        lineterminator="\n",
    )
    _write_json(
        run_dir / assignment_filename,
        serialize_assignment_fixture(file_content, result.solution, result.score),
    )
    return {
        "scheduleArtifact": schedule_filename,
        "assignmentArtifact": assignment_filename,
    }


def _attainment_score(threshold_reach_seconds: dict[int, float], timeout: int) -> float:
    rewards = [
        max(0.0, 1 - threshold_reach_seconds.get(threshold, timeout) / timeout) for threshold in ATTAINMENT_THRESHOLDS
    ]
    return round(100 * statistics.fmean(rewards), 6)


def _run_compute_child(args: argparse.Namespace) -> int:
    threshold_reach_seconds: dict[int, float] = {}
    solving_started_seconds = None
    exporting_started_seconds = None
    workload_started_at = time.monotonic()
    progress_path = args.run_dir / "progress.jsonl"
    file_content = REAL_TESTCASE.read_bytes()

    with progress_path.open("w", encoding="utf-8") as progress_file:

        def record_progress(payload: SchedulePhaseProgress | SolverProgress) -> None:
            nonlocal solving_started_seconds, exporting_started_seconds
            if isinstance(payload, SchedulePhaseProgress):
                serialized = serialize_schedule_phase_progress(payload)
                if payload.code == "solving":
                    solving_started_seconds = payload.elapsedSeconds
                elif payload.code == "exporting":
                    exporting_started_seconds = payload.elapsedSeconds
            else:
                serialized = serialize_solver_progress(payload)
                for threshold in ATTAINMENT_THRESHOLDS:
                    if threshold not in threshold_reach_seconds and payload.currentBestScore >= threshold:
                        threshold_reach_seconds[threshold] = payload.elapsedSeconds
            progress_file.write(json.dumps(serialized, sort_keys=True) + "\n")

        result = nurse_scheduling.schedule(
            file_content,
            prettify=False,
            solver=SOLVER,
            timeout=args.timeout,
            progress_callback=record_progress,
            should_stop=lambda: ATTAINMENT_THRESHOLDS[-1] in threshold_reach_seconds,
        )

    workload_seconds = round(time.monotonic() - workload_started_at, 6)
    solver_seconds = None
    if solving_started_seconds is not None and exporting_started_seconds is not None:
        solver_seconds = round(exporting_started_seconds - solving_started_seconds, 3)
    reached_top_threshold = ATTAINMENT_THRESHOLDS[-1] in threshold_reach_seconds
    time_to_top_threshold_seconds = threshold_reach_seconds.get(ATTAINMENT_THRESHOLDS[-1], args.timeout)
    completed_criterion = reached_top_threshold or (
        solver_seconds is not None and solver_seconds >= args.timeout * 0.95
    )
    run_result = {
        "run": args.run_number,
        "warmup": args.warmup,
        "startedAt": args.started_at,
        "finishedAt": _utc_now(),
        "mode": COMPUTE_MODE,
        "solver": SOLVER,
        "timeoutSeconds": args.timeout,
        "completedCriterion": completed_criterion,
        "stopReason": "top_threshold" if reached_top_threshold else "wall_time",
        "topThresholdReached": reached_top_threshold,
        "timeToTopThresholdSeconds": time_to_top_threshold_seconds,
        "timeToTopThresholdCensored": not reached_top_threshold,
        "attainmentScore": _attainment_score(threshold_reach_seconds, args.timeout),
        "thresholdReachSeconds": {
            str(threshold): threshold_reach_seconds.get(threshold) for threshold in ATTAINMENT_THRESHOLDS
        },
        "score": result.score,
        "status": result.solver_status,
        "solverSeconds": solver_seconds,
        "endToEndSeconds": workload_seconds,
    }
    run_result.update(_write_schedule_artifacts(args.run_dir, file_content, result))
    _write_json(args.run_dir / "result.json", run_result)
    return 0 if completed_criterion and result.score is not None else 1


def _run_search_child(args: argparse.Namespace) -> int:
    workload_started_at = time.monotonic()
    target_reached = False
    target_solver_seconds = None
    target_end_to_end_seconds = None
    solving_started_seconds = None
    exporting_started_seconds = None
    progress_path = args.run_dir / "progress.jsonl"
    file_content = REAL_TESTCASE.read_bytes()

    with progress_path.open("w", encoding="utf-8") as progress_file:

        def record_progress(payload: SchedulePhaseProgress | SolverProgress) -> None:
            nonlocal target_reached, target_solver_seconds, target_end_to_end_seconds
            nonlocal solving_started_seconds, exporting_started_seconds
            if isinstance(payload, SchedulePhaseProgress):
                serialized = serialize_schedule_phase_progress(payload)
                if payload.code == "solving":
                    solving_started_seconds = payload.elapsedSeconds
                elif payload.code == "exporting":
                    exporting_started_seconds = payload.elapsedSeconds
            else:
                serialized = serialize_solver_progress(payload)
                if (
                    args.target_score is not None
                    and not target_reached
                    and payload.currentBestScore >= args.target_score
                ):
                    target_reached = True
                    target_solver_seconds = payload.elapsedSeconds
                    target_end_to_end_seconds = round(time.monotonic() - workload_started_at, 3)
            progress_file.write(json.dumps(serialized, sort_keys=True) + "\n")
            progress_file.flush()

        result = nurse_scheduling.schedule(
            file_content,
            prettify=False,
            solver=SOLVER,
            timeout=args.timeout,
            progress_callback=record_progress,
            should_stop=(lambda: target_reached) if args.target_score is not None else None,
        )

    workload_seconds = round(time.monotonic() - workload_started_at, 3)
    solver_seconds = None
    if solving_started_seconds is not None and exporting_started_seconds is not None:
        solver_seconds = round(exporting_started_seconds - solving_started_seconds, 3)
    run_result = {
        "run": args.run_number,
        "warmup": False,
        "startedAt": args.started_at,
        "finishedAt": _utc_now(),
        "mode": SEARCH_MODE,
        "solver": SOLVER,
        "timeoutSeconds": args.timeout,
        "targetScore": args.target_score,
        "targetReached": target_reached,
        "targetSolverSeconds": target_solver_seconds,
        "targetEndToEndSeconds": target_end_to_end_seconds,
        "score": result.score,
        "status": result.solver_status,
        "solverSeconds": solver_seconds,
        "endToEndSeconds": workload_seconds,
    }
    run_result.update(_write_schedule_artifacts(args.run_dir, file_content, result))
    _write_json(args.run_dir / "result.json", run_result)
    return 0 if result.score is not None else 1


def _run_child(args: argparse.Namespace) -> int:
    if args.mode == COMPUTE_MODE:
        return _run_compute_child(args)
    return _run_search_child(args)


def _numeric_summary(values: list[int | float]) -> dict[str, int | float | None] | None:
    if not values:
        return None
    mean = statistics.fmean(values)
    sample_variance = statistics.variance(values) if len(values) > 1 else None
    sample_standard_deviation = statistics.stdev(values) if len(values) > 1 else None
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(mean, 6),
        "max": max(values),
        "sampleVariance": round(sample_variance, 6) if sample_variance is not None else None,
        "sampleStandardDeviation": (
            round(sample_standard_deviation, 6) if sample_standard_deviation is not None else None
        ),
        "coefficientOfVariationPercent": (
            round(abs(sample_standard_deviation / mean * 100), 6)
            if sample_standard_deviation is not None and mean
            else None
        ),
    }


def _summarize_runs(runs: list[dict[str, Any]], target_score: int | None) -> dict[str, Any]:
    completed = [run for run in runs if run.get("score") is not None and run.get("error") is None]
    summary = {
        "requestedRuns": len(runs),
        "completedRuns": len(completed),
        "score": _numeric_summary([run["score"] for run in completed]),
        "solverSeconds": _numeric_summary(
            [run["solverSeconds"] for run in completed if run["solverSeconds"] is not None]
        ),
        "endToEndSeconds": _numeric_summary([run["endToEndSeconds"] for run in completed]),
    }
    if target_score is not None:
        reached = [run for run in completed if run["targetReached"]]
        summary.update(
            {
                "targetScore": target_score,
                "targetReachedRuns": len(reached),
                "targetSolverSeconds": _numeric_summary([run["targetSolverSeconds"] for run in reached]),
                "targetEndToEndSeconds": _numeric_summary([run["targetEndToEndSeconds"] for run in reached]),
            }
        )
    return summary


def _summarize_compute_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [run for run in runs if run.get("completedCriterion") and run.get("error") is None]
    time_to_top_threshold = _numeric_summary([run["timeToTopThresholdSeconds"] for run in completed])
    median_time = time_to_top_threshold["median"] if time_to_top_threshold is not None else None
    return {
        "requestedRuns": len(runs),
        "completedRuns": len(completed),
        "topThresholdReachedRuns": sum(run["topThresholdReached"] for run in completed),
        "performanceScore": (
            round(100 * PERFORMANCE_REFERENCE_TIME_SECONDS / median_time, 6)
            if median_time is not None and median_time > 0
            else None
        ),
        "timeToTopThresholdSeconds": time_to_top_threshold,
        "attainmentScore": _numeric_summary([run["attainmentScore"] for run in completed]),
        "finalScore": _numeric_summary([run["score"] for run in completed]),
        "solverSeconds": _numeric_summary([run["solverSeconds"] for run in completed]),
        "endToEndSeconds": _numeric_summary([run["endToEndSeconds"] for run in completed]),
    }


def _markdown_compute_report(report: dict[str, Any]) -> str:
    config = report["config"]
    summary = report["summary"]
    performance_score = summary.get("performanceScore")
    final_score = performance_score if performance_score is not None else "unavailable"
    time_to_top_threshold = summary.get("timeToTopThresholdSeconds")
    average_time = time_to_top_threshold["mean"] if time_to_top_threshold is not None else "unavailable"
    lines = [
        "# OR-Tools Real-Case Performance Benchmark",
        "",
        f"- Final score: **{final_score}**",
        f"- Average time to top threshold: **{average_time} seconds**",
        f"- Top threshold reached: {summary['topThresholdReachedRuns']} of {summary['completedRuns']} measured runs",
        f"- Performance reference time: {config['performanceReferenceTimeSeconds']} seconds",
        f"- App version: `{report['environment']['appVersion']}`",
        f"- OR-Tools version: `{report['environment']['ortoolsVersion']}`",
        f"- CPU: {report['environment']['cpuModel'] or 'unknown'}",
        f"- Available logical CPUs: {len(report['environment']['cpuAffinity'] or []) or report['environment']['logicalCpuCount']}",
        (
            f"- Configuration: {config['warmupRuns']} warm-up and {config['runs']} measured runs, "
            f"{config['timeoutSeconds']}-second hard limit or top-threshold attainment"
        ),
        "",
        "| Run | Status | Time to top threshold | Reached | Attainment score | Final objective | Solver seconds | End-to-end seconds |",
        "| ---: | --- | ---: | :---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        lines.append(
            f"| {run['run']} | {run.get('status', 'ERROR')} | {run.get('timeToTopThresholdSeconds', '')} | "
            f"{'yes' if run.get('topThresholdReached') else 'no'} | {run.get('attainmentScore', '')} | "
            f"{run.get('score', '')} | {run.get('solverSeconds', '')} | {run.get('endToEndSeconds', '')} |"
        )
    lines.extend(["", "## Aggregate", ""])
    for label, key in (
        ("Time to top threshold", "timeToTopThresholdSeconds"),
        ("Attainment score", "attainmentScore"),
        ("Final objective", "finalScore"),
        ("Solver seconds", "solverSeconds"),
        ("End-to-end seconds", "endToEndSeconds"),
    ):
        values = summary.get(key)
        if values is not None:
            lines.append(
                f"- {label}: median {values['median']}, mean {values['mean']}, "
                f"range {values['min']} to {values['max']}, "
                f"standard deviation {values['sampleStandardDeviation']}"
            )
    lines.extend(
        [
            "",
            (
                "The final score is 100 times the reference time divided by the median time to "
                "the top threshold. Higher is faster, and score ratios represent inverse "
                "median-time ratios. A run that does not reach the threshold uses the hard "
                "timeout as a censored time. The attainment score remains a secondary measure "
                "of progress across the objective threshold ladder."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_search_report(report: dict[str, Any]) -> str:
    config = report["config"]
    lines = [
        "# OR-Tools Real-Case Performance Benchmark",
        "",
        f"- App version: `{report['environment']['appVersion']}`",
        f"- OR-Tools version: `{report['environment']['ortoolsVersion']}`",
        f"- CPU: {report['environment']['cpuModel'] or 'unknown'}",
        f"- Available logical CPUs: {len(report['environment']['cpuAffinity'] or []) or report['environment']['logicalCpuCount']}",
        f"- Run configuration: {config['runs']} independent runs, {config['timeoutSeconds']} seconds each",
    ]
    if config["targetScore"] is not None:
        lines.append(f"- Target score: {config['targetScore']}")
    lines.extend(
        [
            "",
            "| Run | Status | Score | Solver seconds | End-to-end seconds | Target reached |",
            "| ---: | --- | ---: | ---: | ---: | :---: |",
        ]
    )
    for run in report["runs"]:
        lines.append(
            f"| {run['run']} | {run.get('status', 'ERROR')} | {run.get('score', '')} | "
            f"{run.get('solverSeconds', '')} | {run.get('endToEndSeconds', '')} | "
            f"{'yes' if run.get('targetReached') else 'no'} |"
        )
    summary = report["summary"]
    lines.extend(["", "## Aggregate", ""])
    if config["targetScore"] is not None:
        lines.append(f"- Target reached: {summary['targetReachedRuns']} of {summary['completedRuns']} completed runs")
    for label, key in (
        ("Score", "score"),
        ("Solver seconds", "solverSeconds"),
        ("End-to-end seconds", "endToEndSeconds"),
        ("Target solver seconds", "targetSolverSeconds"),
        ("Target end-to-end seconds", "targetEndToEndSeconds"),
    ):
        values = summary.get(key)
        if values is not None:
            lines.append(
                f"- {label}: median {values['median']}, mean {values['mean']}, range {values['min']} to {values['max']}"
            )
    lines.append("")
    return "\n".join(lines)


def _markdown_report(report: dict[str, Any]) -> str:
    if report["config"]["mode"] == COMPUTE_MODE:
        return _markdown_compute_report(report)
    return _markdown_search_report(report)


def _run_parent(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    environment = _environment_metadata()
    runs = []
    warmups = []

    def execute_run(run_number: int, *, warmup: bool) -> dict[str, Any]:
        directory_prefix = "warmup" if warmup else "run"
        run_dir = output_dir / f"{directory_prefix}-{run_number:03d}"
        run_dir.mkdir()
        started_at = _utc_now()
        command = [
            sys.executable,
            "-m",
            "tests.real.performance_benchmark",
            "--child",
            "--run-dir",
            str(run_dir),
            "--run-number",
            str(run_number),
            "--started-at",
            started_at,
            "--mode",
            args.mode,
            "--timeout",
            str(args.timeout),
        ]
        if warmup:
            command.append("--warmup")
        if args.target_score is not None:
            command.extend(["--target-score", str(args.target_score)])
        run_kind = "warm-up" if warmup else "measured run"
        run_total = args.warmup_runs if warmup else args.runs
        print(f"Starting {run_kind} {run_number}/{run_total}", flush=True)
        process_started_at = time.monotonic()
        with (run_dir / "run.log").open("w", encoding="utf-8") as log_file:
            completed = subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT, check=False)
        process_seconds = round(time.monotonic() - process_started_at, 3)
        result_path = run_dir / "result.json"
        if result_path.is_file():
            run_result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            run_result = {"run": run_number, "startedAt": started_at, "error": "run produced no result"}
        run_result["processSeconds"] = process_seconds
        run_result["exitCode"] = completed.returncode
        _write_json(result_path, run_result)
        print(
            f"Finished {run_kind} {run_number}/{run_total}: status={run_result.get('status', 'ERROR')} "
            f"attainment_score={run_result.get('attainmentScore')} score={run_result.get('score')} "
            f"end_to_end={run_result.get('endToEndSeconds')}s",
            flush=True,
        )
        return run_result

    for run_number in range(1, args.warmup_runs + 1):
        warmups.append(execute_run(run_number, warmup=True))
    for run_number in range(1, args.runs + 1):
        runs.append(execute_run(run_number, warmup=False))

    report = {
        "createdAt": _utc_now(),
        "scenario": {
            "path": str(REAL_TESTCASE.relative_to(REPOSITORY_ROOT)),
            "sha256": hashlib.sha256(REAL_TESTCASE.read_bytes()).hexdigest(),
        },
        "config": {
            "mode": args.mode,
            "solver": SOLVER,
            "runs": args.runs,
            "warmupRuns": args.warmup_runs,
            "timeoutSeconds": args.timeout,
            "targetScore": args.target_score,
            "deterministicSolver": False,
            "interleaveSearch": False,
            "stopCriterion": ("top_attainment_threshold_or_wall_time" if args.mode == COMPUTE_MODE else "search_limit"),
            "solverParameters": "defaults except wall-time limit",
            "parallelism": "solver default using CPUs available to the container",
            "attainmentThresholds": list(ATTAINMENT_THRESHOLDS),
            "attainmentFormula": "100 * mean(max(0, 1 - first_reach_seconds / timeout))",
            "performanceReferenceTimeSeconds": PERFORMANCE_REFERENCE_TIME_SECONDS,
            "performanceScoreFormula": ("100 * reference_time_seconds / median(time_to_top_threshold_seconds)"),
            "timeToTopThresholdTimeoutHandling": (
                "unreached thresholds use timeoutSeconds and are reported as censored"
            ),
        },
        "environment": environment,
        "warmups": warmups,
        "runs": runs,
        "summary": (
            _summarize_compute_runs(runs) if args.mode == COMPUTE_MODE else _summarize_runs(runs, args.target_score)
        ),
    }
    _write_json(output_dir / "report.json", report)
    (output_dir / "summary.md").write_text(_markdown_report(report), encoding="utf-8")
    claimed_performance_env = _claimed_performance_env(report)
    if claimed_performance_env is not None:
        claimed_performance_path = output_dir / "claimed-performance.env"
        claimed_performance_path.write_text(claimed_performance_env, encoding="utf-8")
        print(f"Server claimed-performance settings: {claimed_performance_path}")
    print(f"Benchmark report: {output_dir / 'summary.md'}")
    return 0 if report["summary"]["completedRuns"] == args.runs else 1


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=(COMPUTE_MODE, SEARCH_MODE),
        default=COMPUTE_MODE,
        help="Benchmark normalized threshold attainment or nondeterministic terminal search quality",
    )
    parser.add_argument("--runs", type=_positive_int, default=None, help="Number of measured solver processes")
    parser.add_argument(
        "--warmup-runs",
        type=_nonnegative_int,
        default=None,
        help="Number of unmeasured warm-up processes",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_int,
        default=None,
        help="Hard solver limit per run in seconds",
    )
    parser.add_argument(
        "--target-score",
        type=int,
        help="Stop each run at this score or higher, while retaining --timeout as a hard limit",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="New directory for the benchmark report")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-number", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--started-at", help=argparse.SUPPRESS)
    parser.add_argument("--warmup", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runs is None:
        args.runs = DEFAULT_COMPUTE_RUNS if args.mode == COMPUTE_MODE else DEFAULT_SEARCH_RUNS
    if args.warmup_runs is None:
        args.warmup_runs = DEFAULT_WARMUP_RUNS if args.mode == COMPUTE_MODE else 0
    if args.timeout is None:
        args.timeout = DEFAULT_COMPUTE_TIMEOUT_SECONDS if args.mode == COMPUTE_MODE else DEFAULT_SEARCH_TIMEOUT_SECONDS
    if args.mode == COMPUTE_MODE and args.target_score is not None:
        parser.error("--target-score requires --mode search")
    if args.child:
        if args.run_dir is None or args.run_number is None or args.started_at is None:
            parser.error("child mode requires --run-dir, --run-number, and --started-at")
    else:
        args.output_dir = args.output_dir or _default_output_dir()
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return _run_child(args) if args.child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
