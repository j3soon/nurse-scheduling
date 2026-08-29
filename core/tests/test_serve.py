"""Tests for the optimization HTTP API."""

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

import asyncio
import json
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.scheduler import CANONICAL_SOLVER_CHOICES, ScheduleResult
from nurse_scheduling.server.app import create_app
from nurse_scheduling.server.config import (
    DEFAULT_JOB_RETENTION_SECONDS,
    DEFAULT_MAX_EVENTS_PER_JOB,
    DEFAULT_MAX_RETAINED_JOBS,
    DEFAULT_TIMEOUT_GRACE_SECONDS,
    ClaimedPerformance,
    ServerSettings,
)
from nurse_scheduling.server.jobs.controller import JobController
from nurse_scheduling.server.jobs.models import (
    Job,
    JobFailure,
    JobRequest,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
    WorkerLease,
)
from nurse_scheduling.server.jobs.process_executor import (
    ChildOptimizationError,
    ProcessControl,
    ProcessResult,
    ProcessStatus,
    run_optimization_process,
)
from nurse_scheduling.server.jobs.runner import OptimizationRunner, RunOutput
from nurse_scheduling.server.jobs.worker import JobWorker
from nurse_scheduling.server.runtime_identity import get_deployment_id
from nurse_scheduling.server.solver_capabilities import SOLVER_CAPABILITIES
from nurse_scheduling.server.solver_options import solver_is_available
from nurse_scheduling.server.stores.memory import MemoryJobStore

PROCESS_START_TIMEOUT_SECONDS = 10


class SuccessfulRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        event_callback("job.phase_changed", {"message": "Solving"}, None)
        event_callback("job.progressed", {"current_best_score": 42}, 42)
        return RunOutput(
            result=OptimizationResult(
                outcome=OptimizationOutcome.OPTIMAL,
                score=42,
                solver_status="OPTIMAL",
                termination_reason="optimality_proven",
            ),
            artifact=StoredArtifact(
                name="schedule.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content=b"fake xlsx",
            ),
        )


class InfeasibleRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        return RunOutput(
            result=OptimizationResult(
                outcome=OptimizationOutcome.INFEASIBLE,
                score=None,
                solver_status="INFEASIBLE",
                termination_reason="infeasibility_proven",
            ),
            artifact=None,
        )


class FailingRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        raise RuntimeError("solver exploded")


class NoSolutionRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        return JobFailure(
            code="no_solution_found",
            message="No schedule was produced. Solver status: UNKNOWN",
        )


class StoppableRunner:
    def __init__(self):
        context = multiprocessing.get_context("spawn")
        self.started = context.Event()
        self.finished = context.Event()

    def run(self, job, input_bytes, *, event_callback, should_stop):
        self.started.set()
        event_callback(
            "job.phase_changed",
            {"code": "solving", "message": "Solving"},
            None,
        )
        while should_stop is not None and not should_stop():
            time.sleep(0.005)
        self.finished.set()
        return RunOutput(
            result=OptimizationResult(
                outcome=OptimizationOutcome.FEASIBLE,
                score=7,
                solver_status="FEASIBLE",
                termination_reason="user_requested",
            ),
            artifact=StoredArtifact("schedule.xlsx", "application/test", b"partial"),
        )


class HangingRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        event_callback(
            "job.phase_changed",
            {"code": "solving", "message": "Solving"},
            None,
        )
        while True:
            time.sleep(1)


class PreSolveHangingRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        while True:
            time.sleep(1)


class IgnoringStopRunner:
    def __init__(self):
        self.started = multiprocessing.get_context("spawn").Event()

    def run(self, job, input_bytes, *, event_callback, should_stop):
        self.started.set()
        event_callback(
            "job.phase_changed",
            {"code": "solving", "message": "Solving"},
            None,
        )
        while True:
            time.sleep(1)


class SlowTerminalMessage:
    def __reduce__(self):
        time.sleep(4)
        return SlowTerminalMessage, ()


class SlowTerminalMessageRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        return SlowTerminalMessage()


class AbruptExitRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        os._exit(7)


class DelayedNativeTimeoutRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        time.sleep(0.15)
        event_callback(
            "job.phase_changed",
            {"code": "solving", "message": "Solving"},
            None,
        )
        time.sleep(0.08)
        event_callback(
            "job.phase_changed",
            {"code": "exporting", "message": "Exporting"},
            None,
        )
        time.sleep(0.15)
        return RunOutput(
            result=OptimizationResult(
                outcome=OptimizationOutcome.FEASIBLE,
                score=7,
                solver_status="FEASIBLE",
                termination_reason="solver_timeout",
            ),
            artifact=StoredArtifact("schedule.xlsx", "application/test", b"partial"),
        )


def _settings(**updates) -> ServerSettings:
    values = {
        "claim_poll_seconds": 0.005,
        "maintenance_interval_seconds": 60,
        "sse_keepalive_seconds": 0.01,
    }
    values.update(updates)
    return ServerSettings(**values)


def _client(runner=None, *, start_background=True, settings=None) -> TestClient:
    app = create_app(
        settings=settings or _settings(),
        store=MemoryJobStore(),
        runner=runner or SuccessfulRunner(),
        start_background=start_background,
    )
    return TestClient(app)


def _create(client: TestClient, **data):
    return client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n", **data})


def _wait_for_terminal(
    client: TestClient,
    job_id: str,
    timeout: float = PROCESS_START_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/optimize/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["terminal"]:
            return body
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish: {job_id}")


def _wait_for_worker_ready(worker: JobWorker, timeout: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while not worker.is_ready() and time.monotonic() < deadline:
        time.sleep(0.005)
    return worker.is_ready()


def _install_waiting_process_executor(monkeypatch) -> threading.Event:
    process_started = threading.Event()

    def wait_for_control(runner, job, input_bytes, *, event_callback, control, **_kwargs):
        process_started.set()
        while True:
            requested = control()
            if requested is ProcessControl.FINISH:
                output = runner.run(
                    job,
                    input_bytes,
                    event_callback=event_callback,
                    should_stop=lambda: True,
                )
                return ProcessResult(status=ProcessStatus.COMPLETED, output=output)
            if requested is ProcessControl.CANCEL:
                return ProcessResult(status=ProcessStatus.CANCELLED)
            if requested is ProcessControl.ABORT:
                return ProcessResult(status=ProcessStatus.ABORTED)
            time.sleep(0.001)

    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.worker.run_optimization_process",
        wait_for_control,
    )
    return process_started


def test_info_and_readiness_report_status_without_caching():
    with _client(start_background=False) as client:
        info = client.get("/info")
        ready = client.get("/ready")

        assert info.json() == {
            "status": "ready",
            "service_name": "nurse-scheduling-api",
            "api_version": "0.2.0",
            "app_version": client.app.state.app_version,
            "deployment_id": client.app.state.deployment_id,
            "instance_id": client.app.state.instance_id,
            "started_at": client.app.state.started_at.isoformat(),
            "job_backend": "memory",
            "job_store_id": client.app.state.job_store.store_id,
            "claimed_performance": None,
            "jobs": {"running": 0, "queued": 0, "cancelling": 0},
            "workers": {"online": 0},
        }
        assert ready.json() == {"status": "ready"}
        assert info.headers["cache-control"] == "no-store"
        assert ready.headers["cache-control"] == "no-store"
        assert client.get("/health").status_code == 404


def test_info_reports_shared_job_and_worker_activity():
    with _client(start_background=False) as client:
        first = _create(client).json()
        controller = client.app.state.job_controller
        lease = controller.register_worker("test-worker")
        assert lease is not None
        assert controller.claim_next_job(lease) is not None
        second = _create(client).json()

        info = client.get("/info")

        assert info.status_code == 200
        assert info.json()["jobs"] == {"running": 1, "queued": 1, "cancelling": 0}
        assert info.json()["workers"] == {"online": 1}

        client.post(f"/optimize/{first['id']}/cancel")
        client.post(f"/optimize/{second['id']}/cancel")
        controller.complete_cancellation(first["id"], lease)


def test_info_reports_self_claimed_performance_with_provenance():
    claimed_performance = ClaimedPerformance(
        score=41.524445,
        app_version="v0.2.0-66-g959adc4",
        measured_at=datetime(2026, 8, 28, 19, 12, 54, tzinfo=timezone.utc),
    )

    with _client(start_background=False, settings=_settings(claimed_performance=claimed_performance)) as client:
        info = client.get("/info")

        assert info.json()["claimed_performance"] == {
            "score": 41.524445,
            "app_version": "v0.2.0-66-g959adc4",
            "measured_at": "2026-08-28T19:12:54+00:00",
        }


def test_info_reports_cancelling_jobs_separately():
    with _client(start_background=False) as client:
        created = _create(client).json()
        controller = client.app.state.job_controller
        lease = controller.register_worker("test-worker")
        assert lease is not None
        assert controller.claim_next_job(lease) is not None
        controller.cancel_job(created["id"])

        info = client.get("/info")

        assert info.json()["jobs"] == {"running": 0, "queued": 0, "cancelling": 1}
        assert info.json()["workers"] == {"online": 1}


def test_default_memory_store_uses_the_process_instance_identity():
    app = create_app(settings=_settings(), start_background=False)

    assert app.state.job_store.store_id == app.state.instance_id


def test_app_version_prefers_generated_build_artifact(tmp_path, monkeypatch):
    from nurse_scheduling.server import app as server_app

    version_file = tmp_path / ".app-version"
    version_file.write_text("v9.8.7-generated\n", encoding="utf-8")
    monkeypatch.setattr(server_app, "APP_VERSION_FILE", version_file)

    def unexpected_git_call(*_args, **_kwargs):
        raise AssertionError("Git should not run when the build artifact is available")

    monkeypatch.setattr(server_app.subprocess, "check_output", unexpected_git_call)

    assert server_app.get_app_version() == "v9.8.7-generated"


def test_solver_capability_registry_matches_canonical_choices():
    assert tuple(item.value for item in SOLVER_CAPABILITIES) == CANONICAL_SOLVER_CHOICES

    by_value = {item.value: item for item in SOLVER_CAPABILITIES}
    expected = {
        "ortools/cp-sat": (True, True, True),
        "pulp/cbc": (False, False, True),
        "pulp/cuopt": (True, False, True),
    }
    for selector, capabilities in by_value.items():
        assert (
            capabilities.graceful_timeout,
            capabilities.finish_now,
            capabilities.intermediate_scores,
        ) == expected.get(selector, (False, False, False))

    assert by_value["ortools/cp-sat"].label == "OR-Tools | CP-SAT"
    assert by_value["pulp/cuopt"].label == "PuLP | cuOpt"
    assert by_value["pulp/cuopt"].compute == "gpu"


def test_server_info_logging_is_visible_without_external_logging_configuration():
    environment = os.environ.copy()
    environment["DISABLE_SENTRY"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging; "
                "import nurse_scheduling.server.app; "
                "logging.getLogger('nurse_scheduling.server').info('server-info-visible')"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "server-info-visible" in completed.stderr


def test_info_and_readiness_fail_when_job_store_is_unavailable():
    class UnhealthyStore(MemoryJobStore):
        def check_health(self):
            raise ConnectionError("store unavailable")

    app = create_app(
        settings=_settings(),
        store=UnhealthyStore(),
        runner=SuccessfulRunner(),
        start_background=False,
    )
    with TestClient(app) as client:
        info = client.get("/info")
        ready = client.get("/ready")

    assert info.status_code == 503
    assert info.json()["status"] == "unavailable"
    assert info.json()["reason"] == "job_store_unavailable"
    assert info.json()["instance_id"] == app.state.instance_id
    assert ready.status_code == 503
    assert ready.json()["reason"] == "job_store_unavailable"


def test_info_and_readiness_fail_when_job_worker_stops():
    app = create_app(
        settings=_settings(),
        store=MemoryJobStore(),
        runner=SuccessfulRunner(),
    )
    with TestClient(app) as client:
        app.state.job_worker.stop()
        info = client.get("/info")
        ready = client.get("/ready")

    assert info.status_code == 503
    assert info.json()["reason"] == "job_worker_unavailable"
    assert ready.status_code == 503
    assert ready.json()["reason"] == "job_worker_unavailable"


def test_synchronous_store_reads_do_not_block_the_asgi_event_loop():
    class BlockingGetStore(MemoryJobStore):
        def __init__(self):
            super().__init__()
            self.block_reads = False
            self.read_started = threading.Event()
            self.release_reads = threading.Event()

        def get(self, job_id):
            if self.block_reads:
                self.read_started.set()
                self.release_reads.wait(timeout=2)
            return super().get(job_id)

    store = BlockingGetStore()
    app = create_app(
        settings=_settings(),
        store=store,
        runner=SuccessfulRunner(),
        start_background=False,
    )
    created = app.state.job_controller.create_job(
        input_name="input.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=False,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )
    store.block_reads = True

    async def exercise_requests():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            release_timer = threading.Timer(1, store.release_reads.set)
            release_timer.start()
            started_at = time.monotonic()
            job_request = asyncio.create_task(client.get(f"/optimize/{created.id}"))
            try:
                await asyncio.sleep(0)
                info = await client.get("/info")
                info_elapsed = time.monotonic() - started_at
            finally:
                store.release_reads.set()
                release_timer.cancel()
            job_response = await job_request
            return info, info_elapsed, job_response

    info, info_elapsed, job_response = asyncio.run(exercise_requests())

    assert store.read_started.is_set()
    assert info.status_code == 200
    assert info_elapsed < 0.5
    assert job_response.status_code == 200


def test_job_creation_offloads_the_synchronous_store_write():
    class ThreadRecordingStore(MemoryJobStore):
        create_thread_id = None

        def create(self, *args, **kwargs):
            self.create_thread_id = threading.get_ident()
            return super().create(*args, **kwargs)

    store = ThreadRecordingStore()
    app = create_app(
        settings=_settings(),
        store=store,
        runner=SuccessfulRunner(),
        start_background=False,
    )

    async def create_job():
        event_loop_thread_id = threading.get_ident()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        return event_loop_thread_id, response

    event_loop_thread_id, response = asyncio.run(create_job())

    assert response.status_code == 202
    assert store.create_thread_id is not None
    assert store.create_thread_id != event_loop_thread_id


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"claim_poll_seconds": 0}, "claim_poll_seconds must be positive"),
        ({"worker_lease_seconds": 0}, "worker_lease_seconds must be positive"),
        ({"maintenance_interval_seconds": 0}, "maintenance_interval_seconds must be positive"),
        ({"sse_keepalive_seconds": 0}, "sse_keepalive_seconds must be positive"),
        ({"timeout_grace_seconds": 0}, "timeout_grace_seconds must be positive"),
        ({"max_events_per_job": 0}, "max_events_per_job must be positive"),
        (
            {"default_timeout_seconds": 61, "max_timeout_seconds": 60},
            "default_timeout_seconds must not exceed max_timeout_seconds",
        ),
        (
            {"min_timeout_seconds": 31, "default_timeout_seconds": 30},
            "min_timeout_seconds must not exceed default_timeout_seconds",
        ),
        (
            {"solver_ids": ("ortools/cp-sat", "ortools/cp-sat")},
            "solver_ids must not contain duplicates",
        ),
        (
            {"solver_ids": ("pulp/cuopt",), "default_solver": "ortools/cp-sat"},
            "default_solver must be included in solver_ids",
        ),
        (
            {"solver_ids": ("unknown/solver",), "default_solver": "unknown/solver"},
            "Unsupported server solver",
        ),
    ],
)
def test_server_settings_reject_invalid_relationships(updates, message):
    with pytest.raises(ValueError, match=message):
        _settings(**updates)


def test_runtime_deployment_identity_is_shared_within_one_server_launch(monkeypatch):
    supervisor = type("Supervisor", (), {"pid": 123})()
    monkeypatch.setattr("nurse_scheduling.server.runtime_identity.parent_process", lambda: supervisor)
    monkeypatch.setattr("nurse_scheduling.server.runtime_identity.socket.gethostname", lambda: "container-123")
    monkeypatch.setattr("nurse_scheduling.server.runtime_identity._boot_marker", lambda: "boot-123")
    monkeypatch.setattr(
        "nurse_scheduling.server.runtime_identity._process_start_marker",
        lambda _pid: "start-123",
    )

    first = get_deployment_id()
    second = get_deployment_id()

    assert first == second
    assert first.startswith("deployment-")

    monkeypatch.setattr(
        "nurse_scheduling.server.runtime_identity._process_start_marker",
        lambda _pid: "start-456",
    )
    assert get_deployment_id() != first


@pytest.mark.parametrize(
    "name",
    [
        "claim_poll_seconds",
        "worker_lease_seconds",
        "maintenance_interval_seconds",
        "sse_keepalive_seconds",
        "timeout_grace_seconds",
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
def test_server_settings_reject_non_finite_float_values(name, value):
    with pytest.raises(ValueError, match=rf"{name} must be positive"):
        _settings(**{name: value})


def test_server_settings_from_env_reject_non_finite_float(monkeypatch):
    monkeypatch.setenv("JOB_CLAIM_POLL_SECONDS", "nan")

    with pytest.raises(ValueError, match="JOB_CLAIM_POLL_SECONDS must be a positive number"):
        ServerSettings.from_env()


def test_server_settings_retain_up_to_128_jobs_for_24_hours_by_default():
    settings = ServerSettings()

    assert settings.max_pending_jobs == 32
    assert settings.max_retained_jobs == DEFAULT_MAX_RETAINED_JOBS == 128
    assert settings.job_retention_seconds == DEFAULT_JOB_RETENTION_SECONDS == 24 * 60 * 60
    assert settings.max_events_per_job == DEFAULT_MAX_EVENTS_PER_JOB == 1_000
    assert settings.timeout_grace_seconds == DEFAULT_TIMEOUT_GRACE_SECONDS == 90


def test_server_settings_load_optimization_options_from_env(monkeypatch):
    monkeypatch.setenv("OPTIMIZE_SOLVERS", " ORTOOLS/CP-SAT, PULP/CUOPT ")
    monkeypatch.setenv("OPTIMIZE_DEFAULT_SOLVER", " PULP/CUOPT ")
    monkeypatch.setenv("OPTIMIZE_MIN_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("OPTIMIZE_DEFAULT_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("OPTIMIZE_MAX_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("OPTIMIZE_DEFAULT_PRETTIFY", "false")

    settings = ServerSettings.from_env()

    assert settings.solver_ids == ("ortools/cp-sat", "pulp/cuopt")
    assert settings.default_solver == "pulp/cuopt"
    assert settings.min_timeout_seconds == 10
    assert settings.default_timeout_seconds == 120
    assert settings.max_timeout_seconds == 900
    assert settings.default_prettify is False


def test_server_settings_load_claimed_performance_from_env(monkeypatch):
    monkeypatch.setenv("CLAIMED_PERFORMANCE_SCORE", "41.524445")
    monkeypatch.setenv("CLAIMED_PERFORMANCE_APP_VERSION", "v0.2.0-66-g959adc4")
    monkeypatch.setenv("CLAIMED_PERFORMANCE_MEASURED_AT", "2026-08-28T19:12:54.974377+00:00")

    claimed_performance = ServerSettings.from_env().claimed_performance

    assert claimed_performance == ClaimedPerformance(
        score=41.524445,
        app_version="v0.2.0-66-g959adc4",
        measured_at=datetime(2026, 8, 28, 19, 12, 54, 974377, tzinfo=timezone.utc),
    )


def test_server_settings_require_complete_claimed_performance(monkeypatch):
    monkeypatch.setenv("CLAIMED_PERFORMANCE_SCORE", "41.524445")

    with pytest.raises(ValueError, match="must be set together"):
        ServerSettings.from_env()


def test_server_settings_require_timezone_in_claimed_performance_time(monkeypatch):
    monkeypatch.setenv("CLAIMED_PERFORMANCE_SCORE", "41.524445")
    monkeypatch.setenv("CLAIMED_PERFORMANCE_APP_VERSION", "v0.2.0-66-g959adc4")
    monkeypatch.setenv("CLAIMED_PERFORMANCE_MEASURED_AT", "2026-08-28T19:12:54")

    with pytest.raises(ValueError, match="must include a timezone"):
        ServerSettings.from_env()


def test_app_startup_fails_when_a_configured_solver_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "nurse_scheduling.server.solver_options.solver_is_available",
        lambda _solver_id: False,
    )

    with pytest.raises(ValueError, match="Configured solver is unavailable: ortools/cp-sat"):
        create_app(settings=_settings(), start_background=False)


def test_app_startup_fails_when_mathopt_probe_is_not_optimal(monkeypatch):
    from ortools.math_opt.python import mathopt

    result = mathopt.SolveResult(
        termination=mathopt.Termination(reason=mathopt.TerminationReason.INFEASIBLE),
        solve_stats=mathopt.SolveStats(),
    )
    monkeypatch.setattr(mathopt, "solve", lambda _model, _solver_type: result)
    settings = _settings(
        solver_ids=("ortools/mathopt/highs",),
        default_solver="ortools/mathopt/highs",
    )

    with pytest.raises(ValueError, match="Configured solver is unavailable: ortools/mathopt/highs"):
        create_app(settings=settings, start_background=False)


@pytest.mark.parametrize(
    "solver",
    ["ortools/cp-sat", "ortools/mpsolver/cbc", "ortools/mathopt/highs", "pulp/highs"],
)
def test_installed_solver_runtimes_are_available(solver):
    assert solver_is_available(solver)


@pytest.mark.parametrize(
    ("solve_status", "expected"),
    [(RuntimeError("no CUDA device"), False), (-1, False), (1, True)],
)
def test_cuopt_availability_requires_a_successful_probe(monkeypatch, solve_status, expected):
    import pulp

    class ImportableCuOpt:
        def __init__(self, *, msg):
            pass

        def available(self):
            return True

    def solve(_problem, _solver):
        if isinstance(solve_status, Exception):
            raise solve_status
        return solve_status

    monkeypatch.setattr(pulp, "CUOPT", ImportableCuOpt)
    monkeypatch.setattr(pulp.LpProblem, "solve", solve)

    assert solver_is_available("pulp/cuopt") is expected


def test_optimization_options_use_configured_canonical_solver_metadata(monkeypatch):
    monkeypatch.setattr(
        "nurse_scheduling.server.app.validate_solver_availability",
        lambda _solver_ids: None,
    )
    settings = _settings(
        solver_ids=("ortools/cp-sat", "pulp/cuopt"),
        default_solver="pulp/cuopt",
        min_timeout_seconds=10,
        default_timeout_seconds=120,
        max_timeout_seconds=900,
        default_prettify=False,
    )

    with _client(start_background=False, settings=settings) as client:
        response = client.get("/optimize/options")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "schema_version": "alpha",
        "solver": {
            "default": "pulp/cuopt",
            "choices": [
                {
                    "value": "ortools/cp-sat",
                    "label": "OR-Tools | CP-SAT",
                    "compute": "cpu",
                    "timeout": {"default": 120, "minimum": 10, "maximum": 900},
                    "controls": {"cancel_running": True, "finish_now": True},
                },
                {
                    "value": "pulp/cuopt",
                    "label": "PuLP | cuOpt",
                    "compute": "gpu",
                    "timeout": {"default": 120, "minimum": 10, "maximum": 900},
                    "controls": {"cancel_running": True, "finish_now": False},
                },
            ],
        },
        "prettify": {"default": False},
    }


def test_job_creation_enforces_advertised_options():
    settings = _settings(
        min_timeout_seconds=10,
        default_timeout_seconds=30,
        max_timeout_seconds=60,
        default_prettify=False,
    )
    with _client(start_background=False, settings=settings) as client:
        defaulted = _create(client)
        normalized = _create(client, solver=" ORTOOLS/CP-SAT ", timeout="10", prettify="true")
        disabled_solver = _create(client, solver="pulp/cuopt")
        unknown_solver = _create(client, solver="unknown/solver")
        below_minimum = _create(client, timeout="9")
        above_maximum = _create(client, timeout="61")
        non_integer = _create(client, timeout="10.5")

    assert defaulted.status_code == 202
    assert defaulted.json()["request"]["solver"] == "ortools/cp-sat"
    assert defaulted.json()["request"]["prettify"] is False
    assert defaulted.json()["request"]["timeout_seconds"] == 30
    assert normalized.status_code == 202
    assert normalized.json()["request"]["solver"] == "ortools/cp-sat"
    assert normalized.json()["request"]["timeout_seconds"] == 10
    assert normalized.json()["request"]["prettify"] is True
    assert disabled_solver.status_code == 400
    assert disabled_solver.json()["detail"] == "Solver must be one of: ortools/cp-sat"
    assert unknown_solver.status_code == 400
    assert below_minimum.status_code == 400
    assert above_maximum.status_code == 400
    assert non_integer.status_code == 422


def test_create_complete_download_and_delete_job():
    with _client() as client:
        response = _create(client, timeout="30", prettify="true")
        assert response.status_code == 202
        created = response.json()
        assert created["state"] in {"queued", "running", "completed"}
        assert created["request"]["timeout_seconds"] == 30
        assert response.headers["location"] == f"/optimize/{created['id']}"
        assert response.headers["retry-after"] == "1"
        assert "nurse_scheduling_client_id" in response.headers["set-cookie"]
        assert "Max-Age=604800" in response.headers["set-cookie"]

        completed = _wait_for_terminal(client, created["id"])
        assert completed["state"] == "completed"
        assert completed["result"]["outcome"] == "optimal"
        assert completed["result"]["score"] == 42
        assert completed["links"]["schedule"].endswith("/xlsx")

        download = client.get(completed["links"]["schedule"])
        assert download.status_code == 200
        assert download.content == b"fake xlsx"
        assert "x-schedule-score" not in download.headers
        assert "x-schedule-status" not in download.headers

        assert client.delete(f"/optimize/{created['id']}").status_code == 204
        missing = client.get(f"/optimize/{created['id']}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "job_not_found"


def test_server_executes_real_runner_in_child_process():
    testcase = Path("tests/testcases/basics/01_1nurse_1shift_1day.yaml").read_text()
    with _client(OptimizationRunner()) as client:
        created = _create(
            client,
            yaml_content=testcase,
            solver="ortools/cp-sat",
            timeout="5",
            prettify="false",
        ).json()
        completed = _wait_for_terminal(client, created["id"])

        assert completed["state"] == "completed"
        assert completed["result"]["outcome"] == "optimal"
        assert completed["links"]["schedule"].endswith("/xlsx")


def test_infeasible_is_completed_without_artifact():
    with _client(InfeasibleRunner()) as client:
        created = _create(client).json()
        completed = _wait_for_terminal(client, created["id"])

        assert completed["state"] == "completed"
        assert completed["result"]["outcome"] == "infeasible"
        assert completed["links"]["schedule"] is None
        artifact = client.get(f"/optimize/{created['id']}/xlsx")
        assert artifact.status_code == 409
        assert artifact.json()["error"]["code"] == "job_artifact_not_ready"


def test_unexpected_execution_error_becomes_structured_failure():
    with _client(FailingRunner()) as client:
        created = _create(client).json()
        failed = _wait_for_terminal(client, created["id"])

        assert failed["state"] == "failed"
        assert failed["result"] is None
        assert failed["error"]["code"] == "optimization_failed"
        assert "solver exploded" in failed["error"]["message"]


def test_sentry_capture_failure_does_not_mask_job_failure(monkeypatch):
    def fail_capture(*_args):
        raise RuntimeError("Sentry unavailable")

    monkeypatch.setattr("nurse_scheduling.server.jobs.worker.capture_optimize_exception", fail_capture)

    with _client(FailingRunner()) as client:
        created = _create(client).json()
        failed = _wait_for_terminal(client, created["id"])

    assert failed["state"] == "failed"
    assert failed["error"]["code"] == "optimization_failed"
    assert "solver exploded" in failed["error"]["message"]


def test_unknown_scheduler_result_becomes_no_solution_failure():
    with _client(NoSolutionRunner()) as client:
        created = _create(client).json()
        failed = _wait_for_terminal(client, created["id"])

    assert failed["state"] == "failed"
    assert failed["error"] == {
        "code": "no_solution_found",
        "message": "No schedule was produced. Solver status: UNKNOWN",
    }


def test_watchdog_terminates_solver_process_after_timeout_grace():
    settings = _settings(timeout_grace_seconds=0.1)
    with _client(HangingRunner(), settings=settings) as client:
        created = _create(client, timeout="1").json()
        failed = _wait_for_terminal(client, created["id"])

        assert failed["state"] == "failed"
        assert failed["result"] is None
        assert failed["links"]["schedule"] is None
        assert failed["error"] == {
            "code": "process_timeout",
            "message": (
                "The optimization process did not return within the requested 1-second timeout "
                "and 0.1-second timeout grace period. The server terminated the process."
            ),
        }


def test_watchdog_remains_armed_until_terminal_message_is_delivered():
    job = Job(
        id="job_slow_terminal_message",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="pulp/cbc",
            prettify=False,
            timeout_seconds=1,
        ),
        created_at=datetime.now(timezone.utc),
    )

    result = run_optimization_process(
        SlowTerminalMessageRunner(),
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        control=lambda: None,
        hard_timeout_seconds=2,
        finish_now_enabled=False,
    )

    assert result.status is ProcessStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "process_timeout"


def test_executor_reports_abrupt_child_exit_without_waiting_for_timeout():
    job = Job(
        id="job_abrupt_exit",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="pulp/cbc",
            prettify=False,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ChildOptimizationError, match="ChildProcessCommunicationError"):
        run_optimization_process(
            AbruptExitRunner(),
            job,
            b"apiVersion: alpha\n",
            event_callback=lambda *_args: None,
            control=lambda: None,
            hard_timeout_seconds=61,
            finish_now_enabled=False,
        )


@pytest.mark.parametrize(
    ("control", "expected_status"),
    [
        (ProcessControl.CANCEL, ProcessStatus.CANCELLED),
        (ProcessControl.ABORT, ProcessStatus.ABORTED),
    ],
)
def test_executor_returns_controlled_stop(control, expected_status):
    job = Job(
        id=f"job_{control.value}",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="pulp/cbc",
            prettify=False,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )

    result = run_optimization_process(
        HangingRunner(),
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        control=lambda: control,
        hard_timeout_seconds=61,
        finish_now_enabled=False,
    )

    assert result.status is expected_status
    assert result.output is None
    assert result.failure is None


def test_executor_processes_buffered_success_before_abort():
    abort_requested = False

    def publish(*_args):
        nonlocal abort_requested
        abort_requested = True
        time.sleep(0.2)

    result = run_optimization_process(
        SuccessfulRunner(),
        Job(
            id="job_buffered_success",
            state=JobState.RUNNING,
            request=JobRequest(
                input_name="input.yaml",
                client_id="client",
                solver="pulp/cbc",
                prettify=False,
                timeout_seconds=60,
            ),
            created_at=datetime.now(timezone.utc),
        ),
        b"apiVersion: alpha\n",
        event_callback=publish,
        control=lambda: ProcessControl.ABORT if abort_requested else None,
        hard_timeout_seconds=61,
        finish_now_enabled=False,
    )

    assert result.status is ProcessStatus.COMPLETED
    assert result.output is not None
    assert result.output.result.outcome is OptimizationOutcome.OPTIMAL


def test_process_timeout_allows_model_building_within_timeout_grace():
    job = Job(
        id="job_native_timeout",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout_seconds=0.05,
        ),
        created_at=datetime.now(timezone.utc),
    )
    result = run_optimization_process(
        DelayedNativeTimeoutRunner(),
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        control=lambda: None,
        # Include headroom for spawn imports under coverage on macOS.
        hard_timeout_seconds=5.05,
        finish_now_enabled=False,
    )

    assert result.status is ProcessStatus.COMPLETED
    assert result.output is not None
    assert result.output.result.termination_reason == "solver_timeout"
    assert result.output.artifact is not None


def test_process_timeout_does_not_require_solving_phase_event():
    job = Job(
        id="job_pre_solve_timeout",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout_seconds=0.05,
        ),
        created_at=datetime.now(timezone.utc),
    )

    result = run_optimization_process(
        PreSolveHangingRunner(),
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        control=lambda: None,
        hard_timeout_seconds=1.05,
        finish_now_enabled=False,
    )

    assert result.status is ProcessStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "process_timeout"


@pytest.mark.parametrize(
    ("solver_status", "expected_failure"),
    [
        (
            "MODEL_INVALID",
            JobFailure(code="invalid_model", message="The generated solver model is invalid"),
        ),
        (
            "UNKNOWN",
            JobFailure(
                code="no_solution_found",
                message="No schedule was produced. Solver status: UNKNOWN",
            ),
        ),
    ],
)
def test_optimization_runner_returns_expected_failure(monkeypatch, solver_status, expected_failure):
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.scheduler.schedule",
        lambda **_kwargs: ScheduleResult(None, None, None, solver_status, None),
    )
    job = Job(
        id="job_expected_failure",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )

    result = OptimizationRunner().run(
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        should_stop=None,
    )

    assert result == expected_failure


def test_optimization_runner_uses_job_timestamp_for_artifact_name(monkeypatch):
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.scheduler.schedule",
        lambda **_kwargs: ScheduleResult(object(), object(), 42, "OPTIMAL", None),
    )
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.exporter.export_to_excel",
        lambda _dataframe, output, _cell_export_info: output.write(b"xlsx"),
    )
    job = Job(
        id="job_timestamped",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name='unsafe"\r\nname.yaml',
            client_id="client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout_seconds=60,
        ),
        created_at=datetime(2026, 7, 16, 14, 23, 5, tzinfo=timezone.utc),
    )

    output = OptimizationRunner().run(
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        should_stop=None,
    )

    assert output.artifact is not None
    assert output.artifact.name == "nurse-scheduling-20260716T142305Z.xlsx"


@pytest.mark.parametrize(
    ("stop_requested", "termination_reason"),
    [
        (False, "solver_timeout"),
        (True, "user_requested"),
    ],
)
def test_optimization_runner_classifies_feasible_termination(monkeypatch, stop_requested, termination_reason):
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.scheduler.schedule",
        lambda **_kwargs: ScheduleResult(object(), object(), 42, "FEASIBLE", None),
    )
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.exporter.export_to_excel",
        lambda _dataframe, output, _cell_export_info: output.write(b"xlsx"),
    )
    job = Job(
        id="job_feasible",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )

    output = OptimizationRunner().run(
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        should_stop=lambda: stop_requested,
    )

    assert output.result.termination_reason == termination_reason


def test_optimization_runner_ignores_stop_requested_after_solver_returns(monkeypatch):
    stop_requested = threading.Event()

    def return_feasible(**_kwargs):
        assert not stop_requested.is_set()
        return ScheduleResult(object(), object(), 42, "FEASIBLE", None)

    def request_stop_during_export(_dataframe, output, _cell_export_info):
        stop_requested.set()
        output.write(b"xlsx")

    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.scheduler.schedule",
        return_feasible,
    )
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.exporter.export_to_excel",
        request_stop_during_export,
    )
    job = Job(
        id="job_late_stop",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )

    output = OptimizationRunner().run(
        job,
        b"apiVersion: alpha\n",
        event_callback=lambda *_args: None,
        should_stop=stop_requested.is_set,
    )

    assert output.result.termination_reason == "solver_timeout"


def test_worker_exits_when_unreportable_failure_cleanup_fails(monkeypatch):
    job = Job(
        id="job_store_failure",
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )

    class FailingController:
        def __init__(self):
            self.claim_calls = 0
            self.cleanup_attempted = threading.Event()

        def claim_next_job(self, _lease):
            self.claim_calls += 1
            if self.claim_calls == 1:
                return job
            return None

        def register_worker(self, worker_id):
            return WorkerLease(worker_id, "lease-token", datetime.now(timezone.utc) + timedelta(seconds=60))

        def renew_worker(self, lease):
            return WorkerLease(lease.worker_id, lease.token, datetime.now(timezone.utc) + timedelta(seconds=60))

        def unregister_worker(self, _lease):
            self.cleanup_attempted.set()
            raise ConnectionError("store still unavailable")

        def get_input(self, _job_id):
            raise ConnectionError("store unavailable")

        def fail_job(self, _job_id, _failure, *, lease):
            raise ConnectionError("store still unavailable")

    controller = FailingController()
    monkeypatch.setattr("nurse_scheduling.server.jobs.worker.capture_optimize_exception", lambda *_args: None)
    worker = JobWorker(
        controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=60,
    )

    worker.start()
    try:
        assert controller.cleanup_attempted.wait(timeout=1)
        deadline = time.monotonic() + 1
        while worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert not worker.is_alive()
        assert not worker.is_ready()
    finally:
        worker.stop()


def test_worker_recovers_after_releasing_unreportable_failure_lease(monkeypatch):
    store = MemoryJobStore()
    job_ids = iter(["job_first", "job_second"])
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=2, max_retained=4),
        retention_seconds=60,
        worker_lease_seconds=0.15,
        id_factory=lambda: next(job_ids),
    )
    first = controller.create_job(
        input_name="first.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )
    second = controller.create_job(
        input_name="second.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )

    class ControllerWithReportingFailure:
        def __init__(self, delegate):
            self.delegate = delegate
            self.failure_write_attempted = threading.Event()
            self.second_claimed = threading.Event()

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def claim_next_job(self, lease):
            claimed = self.delegate.claim_next_job(lease)
            if claimed is not None and claimed.id == second.id:
                self.second_claimed.set()
            return claimed

        def get_input(self, job_id):
            if job_id == first.id:
                raise ConnectionError("input read failed")
            return self.delegate.get_input(job_id)

        def fail_job(self, job_id, failure, *, lease):
            if job_id == first.id and not self.failure_write_attempted.is_set():
                self.failure_write_attempted.set()
                raise ConnectionError("failure write failed")
            return self.delegate.fail_job(job_id, failure, lease=lease)

    worker_controller = ControllerWithReportingFailure(controller)
    monkeypatch.setattr("nurse_scheduling.server.jobs.worker.capture_optimize_exception", lambda *_args: None)
    worker = JobWorker(
        worker_controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=0.15,
    )

    worker.start()
    try:
        assert worker_controller.failure_write_attempted.wait(timeout=1)
        assert worker_controller.second_claimed.wait(timeout=2)
        assert worker.is_alive()
        assert _wait_for_worker_ready(worker)
        assert controller.get_job(first.id).state.terminal
    finally:
        worker.stop()


def test_worker_uses_registered_lease_expiration_as_heartbeat_deadline():
    class LeaseController:
        def __init__(self):
            self.registration_count = 0
            self.recovered = threading.Event()

        def register_worker(self, worker_id):
            self.registration_count += 1
            if self.registration_count > 1:
                self.recovered.set()
            lifetime_seconds = 0.03 if self.registration_count == 1 else 60
            return WorkerLease(
                worker_id,
                f"lease-token-{self.registration_count}",
                datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds),
            )

        def renew_worker(self, _lease):
            raise ConnectionError("simulated heartbeat outage")

        def unregister_worker(self, _lease):
            return None

        def claim_next_job(self, _lease):
            return None

        def expire_worker_claims(self):
            return []

    controller = LeaseController()
    worker = JobWorker(
        controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=60,
    )

    worker.start()
    try:
        assert controller.recovered.wait(timeout=1)
        assert _wait_for_worker_ready(worker)
    finally:
        worker.stop()


def test_worker_reconciles_renewal_that_committed_before_response_was_lost():
    class ControllerWithLostRenewalResponse:
        def __init__(self):
            self.registration_count = 0
            self.committed_lease = None
            self.response_lost = threading.Event()
            self.renewal_reconciled = threading.Event()
            self.reregistered = threading.Event()

        def register_worker(self, worker_id):
            self.registration_count += 1
            if self.registration_count > 1:
                self.reregistered.set()
            return WorkerLease(
                worker_id,
                f"lease-token-{self.registration_count}",
                datetime.now(timezone.utc) - timedelta(seconds=1),
            )

        def renew_worker(self, lease):
            if self.committed_lease is None:
                self.committed_lease = WorkerLease(
                    lease.worker_id,
                    lease.token,
                    datetime.now(timezone.utc) + timedelta(seconds=60),
                )
                self.response_lost.set()
                raise ConnectionError("renewal committed but response was lost")
            self.renewal_reconciled.set()
            return self.committed_lease

        def unregister_worker(self, _lease):
            return None

        def claim_next_job(self, _lease):
            return None

        def expire_worker_claims(self):
            return []

    worker_controller = ControllerWithLostRenewalResponse()
    worker = JobWorker(
        worker_controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=60,
    )

    worker.start()
    try:
        assert worker_controller.response_lost.wait(timeout=1)
        assert worker_controller.renewal_reconciled.wait(timeout=1)
        assert not worker_controller.reregistered.is_set()
        assert _wait_for_worker_ready(worker)
        assert worker_controller.registration_count == 1
    finally:
        worker.stop()


def test_worker_discards_recovery_lease_if_shutdown_wins_race(monkeypatch):
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        worker_lease_seconds=0.03,
    )

    class ControllerWithBlockedRecovery:
        def __init__(self, delegate):
            self.delegate = delegate
            self.registration_count = 0
            self.recovery_started = threading.Event()
            self.recovery_allowed = threading.Event()

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def register_worker(self, worker_id):
            self.registration_count += 1
            if self.registration_count > 1:
                self.recovery_started.set()
                self.recovery_allowed.wait(timeout=1)
            return self.delegate.register_worker(worker_id)

        def renew_worker(self, _lease):
            raise ConnectionError("simulated heartbeat outage")

    worker_controller = ControllerWithBlockedRecovery(controller)
    worker = JobWorker(
        worker_controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=0.03,
    )

    worker.start()
    try:
        assert worker_controller.recovery_started.wait(timeout=1)
        heartbeat_thread = worker._heartbeat_thread
        assert heartbeat_thread is not None
        monkeypatch.setattr(heartbeat_thread, "join", lambda timeout=None: None)

        worker.stop()
        worker_controller.recovery_allowed.set()
        threading.Thread.join(heartbeat_thread, timeout=1)

        assert not heartbeat_thread.is_alive()
        assert controller.get_activity().online_workers == 0
    finally:
        worker_controller.recovery_allowed.set()
        worker.stop()


def test_cancel_queued_job_is_immediately_terminal():
    with _client(start_background=False) as client:
        created = _create(client).json()
        response = client.post(f"/optimize/{created['id']}/cancel")

        assert response.status_code == 202
        assert response.json()["state"] == "cancelled"
        assert response.json()["error"]["code"] == "cancelled"


def test_cancel_running_job_stops_worker_and_discards_result():
    runner = StoppableRunner()
    with _client(runner) as client:
        created = _create(client).json()
        assert runner.started.wait(timeout=PROCESS_START_TIMEOUT_SECONDS)
        response = client.post(f"/optimize/{created['id']}/cancel")
        assert response.status_code == 202
        assert response.json()["state"] in {"cancelling", "cancelled"}

        cancelled = _wait_for_terminal(client, created["id"])
        assert cancelled["state"] == "cancelled"
        assert cancelled["result"] is None
        assert cancelled["error"] == {
            "code": "cancelled",
            "message": "Optimization cancelled.",
        }
        assert not runner.finished.is_set()


@pytest.mark.parametrize("solver", ["ortools/cp-sat", "pulp/cbc"])
def test_cancellation_immediately_terminates_the_solver_process(solver):
    runner = IgnoringStopRunner()
    settings = _settings(solver_ids=(solver,), default_solver=solver)
    with _client(runner, settings=settings) as client:
        created = _create(client, solver=solver).json()
        assert runner.started.wait(timeout=PROCESS_START_TIMEOUT_SECONDS)
        running = client.get(f"/optimize/{created['id']}").json()
        assert running["controls"]["cancellable"] is True
        response = client.post(f"/optimize/{created['id']}/cancel")
        assert response.status_code == 202

        cancelled = _wait_for_terminal(client, created["id"])

    assert cancelled["state"] == "cancelled"
    assert cancelled["result"] is None
    assert cancelled["links"]["schedule"] is None
    assert cancelled["error"] == {
        "code": "cancelled",
        "message": "Optimization cancelled.",
    }


def test_finish_now_completes_with_current_feasible_result():
    runner = StoppableRunner()
    with _client(runner) as client:
        created = _create(client).json()
        assert runner.started.wait(timeout=PROCESS_START_TIMEOUT_SECONDS)
        response = client.post(f"/optimize/{created['id']}/finish-now")
        assert response.status_code == 202
        assert response.json()["controls"]["early_completion_available"] is False

        completed = _wait_for_terminal(client, created["id"])
        assert completed["state"] == "completed"
        assert completed["result"]["outcome"] == "feasible"
        assert runner.finished.is_set()


def test_worker_renews_presence_during_long_running_job(monkeypatch):
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        worker_lease_seconds=30,
    )
    created = controller.create_job(
        input_name="input.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )

    class ControllerWithRenewalSignal:
        def __init__(self, delegate, process_started):
            self.delegate = delegate
            self.process_started = process_started
            self.initial_expiry = None
            self.worker_renewed = threading.Event()
            self.renewed_expiry = None

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def register_worker(self, worker_id):
            registered = self.delegate.register_worker(worker_id)
            if registered is not None:
                self.initial_expiry = registered.expires_at
            return registered

        def renew_worker(self, lease):
            if not self.process_started.wait(timeout=2):
                raise RuntimeError("execution did not start before worker renewal")
            renewed = self.delegate.renew_worker(lease)
            if renewed:
                self.renewed_expiry = store._workers[lease.worker_id].expires_at
                self.worker_renewed.set()
            return renewed

    process_started = _install_waiting_process_executor(monkeypatch)
    monkeypatch.setattr("nurse_scheduling.server.jobs.worker.CONTROL_POLL_SECONDS", 0.005)
    worker_controller = ControllerWithRenewalSignal(controller, process_started)
    worker = JobWorker(
        worker_controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=30,
    )
    worker._worker_heartbeat_seconds = 0.005

    worker.start()
    try:
        assert process_started.wait(timeout=2)
        assert worker_controller.worker_renewed.wait(timeout=2)
        assert worker_controller.initial_expiry is not None
        assert worker_controller.renewed_expiry > worker_controller.initial_expiry

        running = controller.get_job(created.id)
        assert running.state == JobState.RUNNING
        controller.request_early_completion(created.id)
        for _ in range(200):
            if controller.get_job(created.id).state == JobState.COMPLETED:
                break
            time.sleep(0.005)
        assert controller.get_job(created.id).state == JobState.COMPLETED
    finally:
        worker.stop()


def test_worker_shutdown_stops_child_and_releases_worker_lease():
    now = [datetime.now(timezone.utc)]
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        worker_lease_seconds=30,
        clock=lambda: now[0],
    )
    created = controller.create_job(
        input_name="input.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )
    runner = IgnoringStopRunner()
    worker = JobWorker(
        controller,
        runner,
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=30,
    )

    worker.start()
    try:
        assert runner.started.wait(timeout=PROCESS_START_TIMEOUT_SECONDS)
        worker.stop()

        running = controller.get_job(created.id)
        assert running.state == JobState.RUNNING
        assert running.worker_id == "worker"
        assert not any(
            process.name == f"optimization-job-{created.id}" for process in multiprocessing.active_children()
        )

        assert controller.expire_worker_claims() == [created.id]
        failed = controller.get_job(created.id)
        assert failed.state == JobState.FAILED
        assert failed.failure is not None
        assert failed.failure.code == "worker_lost"
    finally:
        worker.stop()


def test_worker_cancellation_takes_priority_over_concurrent_shutdown(monkeypatch):
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        worker_lease_seconds=30,
    )
    created = controller.create_job(
        input_name="input.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )
    process_started = threading.Event()
    control_selected = threading.Event()
    selected_controls = []

    def fake_run_optimization_process(*_args, control, **_kwargs):
        process_started.set()
        deadline = time.monotonic() + 2
        while control() is not ProcessControl.CANCEL:
            if time.monotonic() >= deadline:
                raise RuntimeError("Worker did not observe cancellation")
            time.sleep(0.005)

        # Emulate shutdown beginning after the worker observed cancellation but
        # before the executor consumes the highest-priority pending control.
        worker._stop.set()
        selected = control()
        selected_controls.append(selected)
        control_selected.set()
        status = ProcessStatus.CANCELLED if selected is ProcessControl.CANCEL else ProcessStatus.ABORTED
        return ProcessResult(status=status)

    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.worker.run_optimization_process",
        fake_run_optimization_process,
    )
    worker = JobWorker(
        controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=30,
    )

    worker.start()
    try:
        assert process_started.wait(timeout=2)
        controller.cancel_job(created.id)
        assert control_selected.wait(timeout=2)
        for _ in range(200):
            if controller.get_job(created.id).state.terminal:
                break
            time.sleep(0.005)

        assert selected_controls == [ProcessControl.CANCEL]
        assert controller.get_job(created.id).state == JobState.CANCELLED
    finally:
        worker.stop()


def test_worker_stops_execution_after_its_lease_expires(monkeypatch):
    now = [datetime.now(timezone.utc)]
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        worker_lease_seconds=30,
        clock=lambda: now[0],
    )
    created = controller.create_job(
        input_name="input.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )

    class ControllerWithTransientStopReadFailure:
        def __init__(self, delegate):
            self.delegate = delegate
            self.stop_read_failed = threading.Event()
            self.next_claim_attempted = threading.Event()
            self.claim_calls = 0

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def claim_next_job(self, lease):
            self.claim_calls += 1
            claimed = self.delegate.claim_next_job(lease)
            if self.claim_calls > 1:
                self.next_claim_attempted.set()
            return claimed

        def is_stop_requested(self, job_id, lease):
            if not self.stop_read_failed.is_set():
                self.stop_read_failed.set()
                raise ConnectionError("store temporarily unavailable")
            return self.delegate.is_stop_requested(job_id, lease)

    worker_controller = ControllerWithTransientStopReadFailure(controller)
    process_started = _install_waiting_process_executor(monkeypatch)
    monkeypatch.setattr("nurse_scheduling.server.jobs.worker.CONTROL_POLL_SECONDS", 0.005)
    worker = JobWorker(
        worker_controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=30,
    )

    worker.start()
    try:
        assert process_started.wait(timeout=2)
        assert worker_controller.stop_read_failed.wait(timeout=2)
        now[0] += timedelta(seconds=31)
        assert controller.expire_worker_claims() == [created.id]
        assert worker_controller.next_claim_attempted.wait(timeout=2)

        failed = controller.get_job(created.id)
        assert failed.state == JobState.FAILED
        assert failed.failure is not None
        assert failed.failure.code == "worker_lost"
        assert worker.is_alive()
    finally:
        worker.stop()


def test_worker_recovers_after_presence_lease_expires(monkeypatch):
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        worker_lease_seconds=0.06,
    )
    created = controller.create_job(
        input_name="input.yaml",
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )

    class ControllerWithRenewalOutage:
        def __init__(self, delegate):
            self.delegate = delegate
            self.registration_count = 0
            self.renewal_outage = threading.Event()
            self.recovered = threading.Event()

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def register_worker(self, worker_id):
            registered = self.delegate.register_worker(worker_id)
            if registered:
                self.registration_count += 1
                if self.registration_count > 1:
                    self.recovered.set()
            return registered

        def renew_worker(self, lease):
            if self.renewal_outage.is_set():
                raise ConnectionError("simulated heartbeat outage")
            return self.delegate.renew_worker(lease)

    worker_controller = ControllerWithRenewalOutage(controller)
    process_started = _install_waiting_process_executor(monkeypatch)
    worker = JobWorker(
        worker_controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        worker_lease_seconds=0.06,
    )

    worker.start()
    try:
        assert process_started.wait(timeout=2)
        worker_controller.renewal_outage.set()
        assert worker_controller.recovered.wait(timeout=2)
        assert _wait_for_worker_ready(worker)
        failed = controller.get_job(created.id)
        assert failed.state == JobState.FAILED
        assert failed.failure is not None
        assert failed.failure.code == "worker_lost"
    finally:
        worker.stop()


def test_event_stream_has_ids_and_domain_event_names():
    with _client() as client:
        created = _create(client).json()
        _wait_for_terminal(client, created["id"])
        response = client.get(f"/optimize/{created['id']}/events")

        assert response.status_code == 200
        assert "id: 1" in response.text
        assert "event: job.state_changed" in response.text
        assert "event: job.phase_changed" in response.text
        assert "event: job.progressed" in response.text
        assert "event: job.result_available" in response.text
        payloads = [
            json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        queued = next(payload for payload in payloads if payload.get("state") == "queued")
        running = next(payload for payload in payloads if payload.get("state") == "running")
        assert queued["runtime"] == client.app.state.runtime_identity
        assert running["runtime"] == client.app.state.runtime_identity
        assert running["worker_id"] == client.app.state.instance_id


def test_event_stream_replays_only_events_after_last_event_id():
    with _client() as client:
        created = _create(client).json()
        _wait_for_terminal(client, created["id"])
        initial = client.get(f"/optimize/{created['id']}/events")
        event_ids = [line.removeprefix("id: ") for line in initial.text.splitlines() if line.startswith("id: ")]

        resumed = client.get(
            f"/optimize/{created['id']}/events",
            headers={"Last-Event-ID": event_ids[-2]},
        )
        resumed_ids = [line.removeprefix("id: ") for line in resumed.text.splitlines() if line.startswith("id: ")]

        assert resumed_ids == event_ids[-1:]


def test_queue_capacity_is_reported_as_429():
    settings = _settings(max_pending_jobs=1, max_retained_jobs=1)
    with _client(start_background=False, settings=settings) as client:
        assert _create(client).status_code == 202
        rejected = _create(client)

        assert rejected.status_code == 429
        assert rejected.headers["retry-after"] == "1"
        assert rejected.json()["error"]["code"] == "job_capacity_exceeded"


def test_input_and_timeout_validation():
    settings = _settings(max_yaml_bytes=10, default_timeout_seconds=30, max_timeout_seconds=60)
    with _client(start_background=False, settings=settings) as client:
        assert client.post("/optimize").status_code == 400
        assert client.post("/optimize", data={"yaml_content": "a", "timeout": "0"}).status_code == 400
        assert client.post("/optimize", data={"yaml_content": "a", "timeout": "61"}).status_code == 400
        assert client.post("/optimize", data={"yaml_content": "x" * 11}).status_code == 413
        accepted = client.post(
            "/optimize",
            files={"file": ("SCHEDULE.YAML", b"x" * 10, "application/x-yaml")},
        )
        assert accepted.status_code == 202
        oversized = client.post(
            "/optimize",
            files={"file": ("schedule.yaml", b"x" * 11, "application/x-yaml")},
        )
        assert oversized.status_code == 413


def test_file_input_uses_configured_limit_above_multipart_text_default():
    max_yaml_bytes = 1024 * 1024 + 1
    settings = _settings(max_yaml_bytes=max_yaml_bytes)
    with _client(start_background=False, settings=settings) as client:
        accepted = client.post(
            "/optimize",
            files={"file": ("schedule.yaml", b"x" * max_yaml_bytes, "application/x-yaml")},
        )
        assert accepted.status_code == 202

        oversized = client.post(
            "/optimize",
            files={"file": ("schedule.yaml", b"x" * (max_yaml_bytes + 1), "application/x-yaml")},
        )
        assert oversized.status_code == 413
