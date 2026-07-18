"""Probe solver timeout and job-control behavior on the large real scenario."""

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

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CORE_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(CORE_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from nurse_scheduling.scheduler import normalize_solver_selector  # noqa: E402
from nurse_scheduling.server.app import create_app  # noqa: E402
from nurse_scheduling.server.config import ServerSettings  # noqa: E402
from nurse_scheduling.server.solver_capabilities import (  # noqa: E402
    SOLVER_CAPABILITIES,
    get_solver_capabilities,
)
from nurse_scheduling.server.stores.memory import MemoryJobStore  # noqa: E402


REAL_TESTCASE = CORE_ROOT / "tests" / "testcases" / "real" / "large-ward-with-87-people-2025-11.yaml"
CBC_INTERMEDIATE_SCORE_TESTCASE = CORE_ROOT / "tests" / "testcases" / "basics" / "01_1nurse_1shift_1day.yaml"
REAL_SCENARIO_UNSUITABLE_SOLVERS = frozenset({"pulp/cbc"})
"""Solvers that cannot reliably exercise every capability on the large scenario."""
ROUND_ORDER = ("timeout", "cancel", "finish-now", "intermediate-scores")
CONFIRMED_SOLVER_CHOICES = tuple(
    capabilities.value
    for capabilities in SOLVER_CAPABILITIES
    if capabilities.timeout
    or capabilities.cancel_running
    or capabilities.finish_now
    or capabilities.intermediate_scores
)
RESULT_MARKER = "SOLVER_CAPABILITY_RESULT="
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_TIMEOUT_GRACE_SECONDS = 50
DEFAULT_CONTROL_TIMEOUT_SECONDS = 60
DEFAULT_CANCEL_DELAY_SECONDS = 2.0
DEFAULT_FINISH_WAIT_SECONDS = 10.0
DEFAULT_CONTROL_GRACE_SECONDS = 15.0
DEFAULT_STARTUP_TIMEOUT_SECONDS = 180.0
MIN_TIMEOUT_EXERCISE_RATIO = 0.8
UNAVAILABLE_TEXT = (
    "not available",
    "unavailable",
    "cannot load",
    "could not load",
    "no executable found",
    "failed to load",
)


@dataclass(frozen=True)
class ProbeConfig:
    """Runtime limits shared by all solver capability rounds."""

    testcase: Path = REAL_TESTCASE
    cbc_intermediate_score_testcase: Path = CBC_INTERMEDIATE_SCORE_TESTCASE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    timeout_grace_seconds: float = DEFAULT_TIMEOUT_GRACE_SECONDS
    control_timeout_seconds: int = DEFAULT_CONTROL_TIMEOUT_SECONDS
    cancel_delay_seconds: float = DEFAULT_CANCEL_DELAY_SECONDS
    finish_wait_seconds: float = DEFAULT_FINISH_WAIT_SECONDS
    control_grace_seconds: float = DEFAULT_CONTROL_GRACE_SECONDS
    startup_timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class RoundReport:
    """Result of one isolated capability round."""

    name: str
    status: str
    detail: str
    solver_available: bool | None = None
    elapsed_seconds: float | None = None
    elapsed_from: str | None = None
    terminal_state: str | None = None
    solver_status: str | None = None
    error_code: str | None = None
    artifact_available: bool | None = None
    worker_stderr_tail: str | None = None


@dataclass(frozen=True)
class SolverReport:
    """Ordered capability results for one solver selector."""

    selector: str
    available: bool | None
    rounds: tuple[RoundReport, ...]


def _round_report(
    name: str,
    status: str,
    detail: str,
    *,
    solver_available: bool | None = None,
    elapsed_seconds: float | None = None,
    elapsed_from: str | None = None,
    job: dict[str, Any] | None = None,
) -> RoundReport:
    """Build a normalized report from an optional API job response."""
    result = job.get("result") if job else None
    error = job.get("error") if job else None
    links = job.get("links") if job else None
    return RoundReport(
        name=name,
        status=status,
        detail=detail,
        solver_available=solver_available,
        elapsed_seconds=round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        elapsed_from=elapsed_from,
        terminal_state=job.get("state") if job else None,
        solver_status=result.get("solver_status") if result else None,
        error_code=error.get("code") if error else None,
        artifact_available=bool(links.get("schedule")) if links else None,
    )


def _looks_unavailable(job: dict[str, Any]) -> bool:
    """Return whether a terminal failure identifies a missing solver runtime."""
    error = job.get("error") or {}
    message = str(error.get("message", "")).lower()
    return error.get("code") == "optimization_failed" and any(text in message for text in UNAVAILABLE_TEXT)


def _wait_for_solving(
    store: MemoryJobStore,
    client: TestClient,
    job_id: str,
    timeout_seconds: float,
) -> tuple[float | None, str | None, dict[str, Any]]:
    """Wait for the solving phase, returning its time, event cursor, and latest job."""
    deadline = time.monotonic() + timeout_seconds
    last_event_id = None
    for event in store.stream_events(job_id, after_id=None, keepalive_seconds=0.05):
        if time.monotonic() >= deadline:
            break
        if event is None:
            continue
        last_event_id = event.id
        if event.type == "job.phase_changed" and event.data.get("code") == "solving":
            return time.monotonic(), last_event_id, client.get(f"/optimize/{job_id}").json()
    return None, last_event_id, client.get(f"/optimize/{job_id}").json()


def _wait_before_control(
    store: MemoryJobStore,
    client: TestClient,
    job_id: str,
    after_id: str | None,
    delay_seconds: float,
    *,
    stop_on_incumbent: bool,
) -> tuple[bool, dict[str, Any]]:
    """Wait briefly after solving starts and optionally stop at the first incumbent."""
    deadline = time.monotonic() + delay_seconds
    for event in store.stream_events(job_id, after_id=after_id, keepalive_seconds=0.05):
        job = client.get(f"/optimize/{job_id}").json()
        if job["terminal"]:
            return False, job
        if event is not None and stop_on_incumbent and event.type == "job.progressed":
            return True, job
        if time.monotonic() >= deadline:
            return False, job
    return False, client.get(f"/optimize/{job_id}").json()


def _wait_for_terminal(client: TestClient, job_id: str, timeout_seconds: float) -> dict[str, Any] | None:
    """Poll one job until it becomes terminal or the deadline passes."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = client.get(f"/optimize/{job_id}").json()
        if job["terminal"]:
            return job
        time.sleep(0.05)
    return None


def _submit_job(client: TestClient, testcase: Path, solver: str, timeout_seconds: int) -> dict[str, Any]:
    """Submit the real scenario through the public optimization endpoint."""
    response = client.post(
        "/optimize",
        files={"file": (testcase.name, testcase.read_bytes(), "application/yaml")},
        data={"solver": solver, "timeout": str(timeout_seconds), "prettify": "false"},
    )
    if response.status_code != 202:
        raise RuntimeError(f"Optimization submission returned HTTP {response.status_code}: {response.text}")
    return response.json()


def _round_testcase(name: str, solver: str, config: ProbeConfig) -> Path:
    """Return the explicit testcase exception for a solver and capability pair."""
    if solver in REAL_SCENARIO_UNSUITABLE_SOLVERS and name == "intermediate-scores":
        return config.cbc_intermediate_score_testcase
    return config.testcase


def _early_terminal_report(name: str, job: dict[str, Any]) -> RoundReport:
    """Classify a job that ended before its solver reached the solving phase."""
    if _looks_unavailable(job):
        return _round_report(
            name,
            "UNAVAILABLE",
            str((job.get("error") or {}).get("message", "Solver runtime is unavailable.")),
            solver_available=False,
            job=job,
        )
    return _round_report(
        name,
        "FAIL",
        "Job ended before the solving phase.",
        solver_available=True,
        job=job,
    )


def _evaluate_timeout(job: dict[str, Any], elapsed_seconds: float, config: ProbeConfig) -> RoundReport:
    """Classify one terminal job observed during the timeout round."""
    if elapsed_seconds > config.timeout_seconds + config.timeout_grace_seconds:
        return _round_report(
            "timeout",
            "FAIL",
            "Solver returned after the timeout budget and grace period.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="solving_started",
            job=job,
        )
    if _looks_unavailable(job):
        return _early_terminal_report("timeout", job)

    result = job.get("result") or {}
    error = job.get("error") or {}
    exercised_timeout = elapsed_seconds >= config.timeout_seconds * MIN_TIMEOUT_EXERCISE_RATIO
    if result.get("termination_reason") == "limit_or_stop" and exercised_timeout:
        return _round_report(
            "timeout",
            "PASS",
            "Solver returned a feasible schedule within the timeout grace period.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="solving_started",
            job=job,
        )
    if error.get("code") == "no_solution_found" and exercised_timeout:
        return _round_report(
            "timeout",
            "PASS",
            "Solver stopped on time before finding a feasible schedule.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="solving_started",
            job=job,
        )
    if result.get("termination_reason") in {"optimality_proven", "infeasibility_proven"}:
        return _round_report(
            "timeout",
            "INCONCLUSIVE",
            "Solver completed before the timeout could be exercised.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="solving_started",
            job=job,
        )
    return _round_report(
        "timeout",
        "FAIL",
        "Job ended without a timeout-related result.",
        solver_available=True,
        elapsed_seconds=elapsed_seconds,
        elapsed_from="solving_started",
        job=job,
    )


def _run_timeout_round(
    client: TestClient,
    store: MemoryJobStore,
    solver: str,
    config: ProbeConfig,
) -> RoundReport:
    """Run the bounded timeout capability check."""
    created = _submit_job(client, _round_testcase("timeout", solver, config), solver, config.timeout_seconds)
    solving_at, _event_id, job = _wait_for_solving(
        store,
        client,
        created["id"],
        config.startup_timeout_seconds,
    )
    if solving_at is None:
        if job["terminal"]:
            return _early_terminal_report("timeout", job)
        return _round_report(
            "timeout",
            "FAIL",
            "Job did not reach the solving phase before the startup watchdog expired.",
            solver_available=None,
            job=job,
        )

    job = _wait_for_terminal(
        client,
        created["id"],
        config.timeout_seconds + config.timeout_grace_seconds,
    )
    elapsed_seconds = time.monotonic() - solving_at
    if job is None:
        return _round_report(
            "timeout",
            "FAIL",
            "Solver ignored the timeout or did not return within the grace period.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="solving_started",
        )
    return _evaluate_timeout(job, elapsed_seconds, config)


def _run_intermediate_scores_round(
    client: TestClient,
    store: MemoryJobStore,
    solver: str,
    config: ProbeConfig,
) -> RoundReport:
    """Confirm that a score event is emitted before solver execution ends."""
    created = _submit_job(
        client,
        _round_testcase("intermediate-scores", solver, config),
        solver,
        config.timeout_seconds,
    )
    solving_at, event_id, job = _wait_for_solving(
        store,
        client,
        created["id"],
        config.startup_timeout_seconds,
    )
    if solving_at is None:
        if job["terminal"]:
            return _early_terminal_report("intermediate-scores", job)
        return _round_report(
            "intermediate-scores",
            "FAIL",
            "Job did not reach the solving phase before the startup watchdog expired.",
            solver_available=None,
            job=job,
        )

    deadline = time.monotonic() + config.timeout_seconds + config.timeout_grace_seconds
    score_seen = False
    for event in store.stream_events(created["id"], after_id=event_id, keepalive_seconds=0.05):
        if event is not None and event.type == "job.progressed":
            source = str(event.data.get("source", ""))
            if not source.endswith(":final-result"):
                score_seen = True
        job = client.get(f"/optimize/{created['id']}").json()
        if job["terminal"]:
            elapsed_seconds = time.monotonic() - solving_at
            if _looks_unavailable(job):
                return _early_terminal_report("intermediate-scores", job)
            if score_seen:
                return _round_report(
                    "intermediate-scores",
                    "PASS",
                    "Solver emitted an intermediate score before returning.",
                    solver_available=True,
                    elapsed_seconds=elapsed_seconds,
                    elapsed_from="solving_started",
                    job=job,
                )
            error_code = (job.get("error") or {}).get("code")
            if error_code in {"no_solution_found", "optimization_failed"}:
                return _round_report(
                    "intermediate-scores",
                    "INCONCLUSIVE",
                    "Solver returned before finding an incumbent that could emit an intermediate score.",
                    solver_available=True,
                    elapsed_seconds=elapsed_seconds,
                    elapsed_from="solving_started",
                    job=job,
                )
            return _round_report(
                "intermediate-scores",
                "FAIL",
                "Solver produced a result without emitting a confirmed intermediate score.",
                solver_available=True,
                elapsed_seconds=elapsed_seconds,
                elapsed_from="solving_started",
                job=job,
            )
        if time.monotonic() >= deadline:
            return _round_report(
                "intermediate-scores",
                "FAIL",
                "Solver did not return within the intermediate-score watchdog.",
                solver_available=True,
                elapsed_seconds=time.monotonic() - solving_at,
                elapsed_from="solving_started",
                job=job,
            )


def _run_control_round(
    name: str,
    client: TestClient,
    store: MemoryJobStore,
    solver: str,
    config: ProbeConfig,
) -> RoundReport:
    """Run cancellation or early completion against a fresh long-running job."""
    created = _submit_job(client, _round_testcase(name, solver, config), solver, config.control_timeout_seconds)
    solving_at, event_id, job = _wait_for_solving(
        store,
        client,
        created["id"],
        config.startup_timeout_seconds,
    )
    if solving_at is None:
        if job["terminal"]:
            return _early_terminal_report(name, job)
        return _round_report(
            name,
            "FAIL",
            "Job did not reach the solving phase before the startup watchdog expired.",
            solver_available=None,
            job=job,
        )

    wait_seconds = config.cancel_delay_seconds if name == "cancel" else config.finish_wait_seconds
    incumbent_seen, job = _wait_before_control(
        store,
        client,
        created["id"],
        event_id,
        wait_seconds,
        stop_on_incumbent=name == "finish-now",
    )
    if job["terminal"]:
        return _round_report(
            name,
            "INCONCLUSIVE",
            "Solver completed before the control request was sent.",
            solver_available=True,
            elapsed_seconds=time.monotonic() - solving_at,
            elapsed_from="solving_started",
            job=job,
        )

    endpoint = "cancel" if name == "cancel" else "finish-now"
    control_requested_at = time.monotonic()
    response = client.post(f"/optimize/{created['id']}/{endpoint}")
    if response.status_code != 202:
        latest = client.get(f"/optimize/{created['id']}").json()
        if latest["terminal"]:
            return _round_report(
                name,
                "INCONCLUSIVE",
                "Job completed while the control request was being sent.",
                solver_available=True,
                elapsed_seconds=time.monotonic() - control_requested_at,
                elapsed_from="control_requested",
                job=latest,
            )
        return _round_report(
            name,
            "FAIL",
            f"Supported control returned unexpected HTTP {response.status_code}.",
            solver_available=True,
            elapsed_seconds=time.monotonic() - control_requested_at,
            elapsed_from="control_requested",
            job=latest,
        )

    terminal = _wait_for_terminal(client, created["id"], config.control_grace_seconds)
    elapsed_seconds = time.monotonic() - control_requested_at
    if terminal is None:
        return _round_report(
            name,
            "FAIL",
            "Solver did not return within the control grace period.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="control_requested",
        )

    if name == "cancel":
        if (
            terminal["state"] == "cancelled"
            and terminal.get("result") is None
            and not terminal["links"].get("schedule")
        ):
            return _round_report(
                name,
                "PASS",
                "Running job was cancelled and produced no retained result.",
                solver_available=True,
                elapsed_seconds=elapsed_seconds,
                elapsed_from="control_requested",
                job=terminal,
            )
        return _round_report(
            name,
            "FAIL",
            "Cancellation returned, but the terminal job retained an unexpected result.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="control_requested",
            job=terminal,
        )

    if terminal["state"] == "completed" and terminal.get("result") is not None and terminal["links"].get("schedule"):
        detail = "Solver stopped and preserved its current feasible schedule."
        if incumbent_seen:
            detail = "Solver stopped after an incumbent event and preserved the schedule."
        return _round_report(
            name,
            "PASS",
            detail,
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="control_requested",
            job=terminal,
        )
    if terminal["state"] == "failed" and (terminal.get("error") or {}).get("code") == "no_solution_found":
        return _round_report(
            name,
            "INCONCLUSIVE",
            "Solver stopped before a feasible incumbent was available.",
            solver_available=True,
            elapsed_seconds=elapsed_seconds,
            elapsed_from="control_requested",
            job=terminal,
        )
    return _round_report(
        name,
        "FAIL",
        "Finish-now produced an unexpected terminal result.",
        solver_available=True,
        elapsed_seconds=elapsed_seconds,
        elapsed_from="control_requested",
        job=terminal,
    )


def _worker_settings(config: ProbeConfig) -> ServerSettings:
    """Build isolated memory-backed server settings for one worker subprocess."""
    return ServerSettings(
        max_pending_jobs=1,
        max_retained_jobs=2,
        claim_poll_seconds=0.01,
        maintenance_interval_seconds=60,
        sse_keepalive_seconds=0.05,
        default_timeout_seconds=config.control_timeout_seconds,
        max_timeout_seconds=max(config.control_timeout_seconds, config.timeout_seconds),
    )


def _run_worker_round(name: str, solver: str, config: ProbeConfig) -> RoundReport:
    """Execute one real round inside the current isolated subprocess."""
    store = MemoryJobStore()
    app = create_app(settings=_worker_settings(config), store=store)
    with TestClient(app) as client:
        if name == "timeout":
            return _run_timeout_round(client, store, solver, config)
        if name == "intermediate-scores":
            return _run_intermediate_scores_round(client, store, solver, config)
        return _run_control_round(name, client, store, solver, config)


def _worker_timeout(name: str, config: ProbeConfig) -> float:
    """Return the parent-process watchdog for one worker round."""
    if name in {"timeout", "intermediate-scores"}:
        active_seconds = config.timeout_seconds + config.timeout_grace_seconds
    else:
        wait_seconds = config.cancel_delay_seconds if name == "cancel" else config.finish_wait_seconds
        active_seconds = wait_seconds + config.control_grace_seconds
    return config.startup_timeout_seconds + active_seconds + 15


def _run_round_subprocess(name: str, solver: str, config: ProbeConfig) -> RoundReport:
    """Run one capability round in a killable child process."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--solver",
        solver,
        "--worker-round",
        name,
        "--testcase",
        str(config.testcase),
        "--cbc-intermediate-score-testcase",
        str(config.cbc_intermediate_score_testcase),
        "--timeout-seconds",
        str(config.timeout_seconds),
        "--timeout-grace-seconds",
        str(config.timeout_grace_seconds),
        "--control-timeout-seconds",
        str(config.control_timeout_seconds),
        "--cancel-delay-seconds",
        str(config.cancel_delay_seconds),
        "--finish-wait-seconds",
        str(config.finish_wait_seconds),
        "--control-grace-seconds",
        str(config.control_grace_seconds),
        "--startup-timeout-seconds",
        str(config.startup_timeout_seconds),
    ]
    environment = os.environ.copy()
    environment.update(DISABLE_SENTRY="1", PYTHONUNBUFFERED="1")
    try:
        completed = subprocess.run(
            command,
            cwd=CORE_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=_worker_timeout(name, config),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _round_report(
            name,
            "FAIL",
            "Worker subprocess exceeded its hard watchdog and was terminated.",
        )

    payload = None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            payload = line.removeprefix(RESULT_MARKER)
            break
    if payload is None:
        stderr_tail = completed.stderr[-2_000:].strip() or None
        return RoundReport(
            name=name,
            status="FAIL",
            detail=f"Worker exited with code {completed.returncode} without a result payload.",
            worker_stderr_tail=stderr_tail,
        )
    try:
        report = RoundReport(**json.loads(payload))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return RoundReport(
            name=name,
            status="FAIL",
            detail=f"Worker returned an invalid result payload: {error}",
            worker_stderr_tail=completed.stderr[-2_000:].strip() or None,
        )
    if completed.returncode != 0:
        return RoundReport(
            **{
                **asdict(report),
                "status": "FAIL",
                "detail": f"Worker exited with code {completed.returncode}: {report.detail}",
                "worker_stderr_tail": completed.stderr[-2_000:].strip() or None,
            }
        )
    if report.status == "FAIL" and completed.stderr.strip():
        return RoundReport(
            **{
                **asdict(report),
                "worker_stderr_tail": completed.stderr[-2_000:].strip(),
            }
        )
    return report


def probe_solver(solver: str, config: ProbeConfig) -> SolverReport:
    """Run the advertised capability rounds for one solver in fixed order."""
    selector = normalize_solver_selector(solver).canonical
    capabilities = get_solver_capabilities(selector)
    if capabilities is None:
        raise ValueError(f"No capability configuration for solver: {selector}")
    enabled = {
        # Always exercise timeout so an unconfirmed solver can gather evidence
        # without changing the conservative server registry first.
        "timeout": True,
        "cancel": capabilities.cancel_running,
        "finish-now": capabilities.finish_now,
        "intermediate-scores": capabilities.intermediate_scores,
    }
    reports: list[RoundReport] = []
    for name in ROUND_ORDER:
        if not enabled[name]:
            reports.append(
                _round_report(
                    name,
                    "NOT_CONFIRMED",
                    "Capability is not confirmed and was not exercised.",
                )
            )
            continue
        if any(report.status == "UNAVAILABLE" for report in reports):
            print(f"[{selector}] {name}: skipped because the solver is unavailable", file=sys.stderr, flush=True)
            reports.append(
                _round_report(
                    name,
                    "UNAVAILABLE",
                    "Skipped because an earlier round found no solver runtime.",
                    solver_available=False,
                )
            )
            continue
        print(f"[{selector}] {name}: running", file=sys.stderr, flush=True)
        report = _run_round_subprocess(name, selector, config)
        print(f"[{selector}] {name}: {report.status}", file=sys.stderr, flush=True)
        reports.append(report)
    available = (
        False
        if any(report.status == "UNAVAILABLE" for report in reports)
        else next(
            (report.solver_available for report in reports if report.solver_available is not None),
            None,
        )
    )
    return SolverReport(selector=selector, available=available, rounds=tuple(reports))


def _status_cell(report: RoundReport) -> str:
    """Format one compact Markdown result cell."""
    if "Unsupported control" in report.detail:
        return f"{report.status} (unsupported)"
    if report.elapsed_seconds is None:
        return report.status
    return f"{report.status} ({report.elapsed_seconds:.1f}s)"


def render_markdown(reports: list[SolverReport]) -> str:
    """Render the human-readable capability summary."""
    lines = [
        "| Selector | Available | Timeout | Cancel | Finish now | Intermediate scores | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        by_name = {round_report.name: round_report for round_report in report.rounds}
        available = "Yes" if report.available is True else "No" if report.available is False else "Unknown"
        notes = " ".join(
            " ".join(f"{round_report.name}: {round_report.detail}".split()) for round_report in report.rounds
        ).replace("|", "\\|")
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{report.selector}`",
                    available,
                    _status_cell(by_name["timeout"]),
                    _status_cell(by_name["cancel"]),
                    _status_cell(by_name["finish-now"]),
                    _status_cell(by_name["intermediate-scores"]),
                    notes,
                )
            )
            + " |"
        )
    return "\n".join(lines)


def _json_payload(reports: list[SolverReport], config: ProbeConfig) -> dict[str, Any]:
    """Build a machine-readable report with runtime context."""
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "pythonVersion": platform.python_version(),
        "testcase": str(config.testcase),
        "roundOrder": list(ROUND_ORDER),
        "config": {
            **asdict(config),
            "testcase": str(config.testcase),
            "cbc_intermediate_score_testcase": str(config.cbc_intermediate_score_testcase),
        },
        "solvers": [asdict(report) for report in reports],
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the public and hidden worker CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Probe solver timeout, cancellation, and finish-now behavior on the large real scenario."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--solver", choices=CONFIRMED_SOLVER_CHOICES, help="Probe one configured solver selector.")
    selection.add_argument("--all", action="store_true", help="Probe every solver with a confirmed capability.")
    parser.add_argument("--testcase", type=Path, default=REAL_TESTCASE)
    parser.add_argument(
        "--cbc-intermediate-score-testcase",
        type=Path,
        default=CBC_INTERMEDIATE_SCORE_TESTCASE,
    )
    parser.add_argument("--timeout-seconds", type=_positive_int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--timeout-grace-seconds", type=_positive_float, default=DEFAULT_TIMEOUT_GRACE_SECONDS)
    parser.add_argument(
        "--control-timeout-seconds",
        type=_positive_int,
        default=DEFAULT_CONTROL_TIMEOUT_SECONDS,
    )
    parser.add_argument("--cancel-delay-seconds", type=_positive_float, default=DEFAULT_CANCEL_DELAY_SECONDS)
    parser.add_argument("--finish-wait-seconds", type=_positive_float, default=DEFAULT_FINISH_WAIT_SECONDS)
    parser.add_argument("--control-grace-seconds", type=_positive_float, default=DEFAULT_CONTROL_GRACE_SECONDS)
    parser.add_argument("--startup-timeout-seconds", type=_positive_float, default=DEFAULT_STARTUP_TIMEOUT_SECONDS)
    parser.add_argument("--json-output", type=Path, help="Also write the full machine-readable report to this path.")
    parser.add_argument("--worker-round", choices=ROUND_ORDER, help=argparse.SUPPRESS)
    return parser


def _config_from_args(args: argparse.Namespace) -> ProbeConfig:
    """Translate validated CLI arguments into immutable probe configuration."""
    return ProbeConfig(
        testcase=args.testcase.resolve(),
        cbc_intermediate_score_testcase=args.cbc_intermediate_score_testcase.resolve(),
        timeout_seconds=args.timeout_seconds,
        timeout_grace_seconds=args.timeout_grace_seconds,
        control_timeout_seconds=args.control_timeout_seconds,
        cancel_delay_seconds=args.cancel_delay_seconds,
        finish_wait_seconds=args.finish_wait_seconds,
        control_grace_seconds=args.control_grace_seconds,
        startup_timeout_seconds=args.startup_timeout_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    """Run one worker round or orchestrate the requested solver probes."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.worker_round is not None:
        if args.solver is None or args.all:
            parser.error("--worker-round requires --solver")
        try:
            report = _run_worker_round(args.worker_round, args.solver, _config_from_args(args))
        except Exception as error:
            traceback.print_exc()
            report = _round_report(args.worker_round, "FAIL", f"Unhandled worker error: {error}")
        print(f"{RESULT_MARKER}{json.dumps(asdict(report), sort_keys=True)}", flush=True)
        return 0

    if args.solver is None and not args.all:
        parser.error("one of --solver or --all is required")
    if not args.testcase.is_file():
        parser.error(f"testcase does not exist: {args.testcase}")
    if not args.cbc_intermediate_score_testcase.is_file():
        parser.error(f"CBC intermediate-score testcase does not exist: {args.cbc_intermediate_score_testcase}")

    config = _config_from_args(args)
    selectors = CONFIRMED_SOLVER_CHOICES if args.all else (args.solver,)
    reports = [probe_solver(selector, config) for selector in selectors]
    print(render_markdown(reports))
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(_json_payload(reports, config), indent=2) + "\n", encoding="utf-8")
    return int(any(round_report.status == "FAIL" for report in reports for round_report in report.rounds))


if __name__ == "__main__":
    raise SystemExit(main())
