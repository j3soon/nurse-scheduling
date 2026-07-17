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
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.scheduler import ScheduleResult
from nurse_scheduling.server.app import create_app
from nurse_scheduling.server.config import (
    DEFAULT_JOB_RETENTION_SECONDS,
    DEFAULT_MAX_EVENTS_PER_JOB,
    DEFAULT_MAX_RETAINED_JOBS,
    ServerSettings,
)
from nurse_scheduling.server.jobs.models import (
    Job,
    JobRequest,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
    solver_supports_stop,
)
from nurse_scheduling.server.jobs.controller import JobController
from nurse_scheduling.server.jobs.runner import OptimizationRunner, RunOutput
from nurse_scheduling.server.jobs.worker import JobWorker
from nurse_scheduling.server.stores.memory import MemoryJobStore


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


class StoppableRunner:
    def __init__(self):
        self.started = threading.Event()
        self.finished = threading.Event()

    def run(self, job, input_bytes, *, event_callback, should_stop):
        self.started.set()
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


def _wait_for_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(300):
        response = client.get(f"/optimize/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["terminal"]:
            return body
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish: {job_id}")


def test_health_and_readiness_report_status():
    with _client(start_background=False) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "apiVersion": "alpha",
            "appVersion": client.app.state.app_version,
        }
        assert client.get("/ready").json() == {"status": "ready"}


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


def test_health_and_readiness_fail_when_job_store_is_unavailable():
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
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 503
    assert health.json()["reason"] == "job_store_unavailable"
    assert ready.status_code == 503
    assert ready.json()["reason"] == "job_store_unavailable"


def test_health_and_readiness_fail_when_job_worker_stops():
    app = create_app(
        settings=_settings(),
        store=MemoryJobStore(),
        runner=SuccessfulRunner(),
    )
    with TestClient(app) as client:
        app.state.job_worker.stop()
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 503
    assert health.json()["reason"] == "job_worker_unavailable"
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
                health = await client.get("/health")
                health_elapsed = time.monotonic() - started_at
            finally:
                store.release_reads.set()
                release_timer.cancel()
            job_response = await job_request
            return health, health_elapsed, job_response

    health, health_elapsed, job_response = asyncio.run(exercise_requests())

    assert store.read_started.is_set()
    assert health.status_code == 200
    assert health_elapsed < 0.5
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
        ({"claim_lease_seconds": 0}, "claim_lease_seconds must be positive"),
        ({"maintenance_interval_seconds": 0}, "maintenance_interval_seconds must be positive"),
        ({"sse_keepalive_seconds": 0}, "sse_keepalive_seconds must be positive"),
        ({"max_events_per_job": 0}, "max_events_per_job must be positive"),
        (
            {"default_timeout_seconds": 61, "max_timeout_seconds": 60},
            "default_timeout_seconds must not exceed max_timeout_seconds",
        ),
    ],
)
def test_server_settings_reject_invalid_relationships(updates, message):
    with pytest.raises(ValueError, match=message):
        _settings(**updates)


@pytest.mark.parametrize(
    "name",
    [
        "claim_poll_seconds",
        "claim_lease_seconds",
        "maintenance_interval_seconds",
        "sse_keepalive_seconds",
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

    assert settings.max_retained_jobs == DEFAULT_MAX_RETAINED_JOBS == 128
    assert settings.job_retention_seconds == DEFAULT_JOB_RETENTION_SECONDS == 24 * 60 * 60
    assert settings.max_events_per_job == DEFAULT_MAX_EVENTS_PER_JOB == 1_000


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


def test_unknown_scheduler_result_becomes_no_solution_failure(monkeypatch):
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.runner.scheduler.schedule",
        lambda **_kwargs: ScheduleResult(None, None, None, "UNKNOWN", None),
    )

    with _client(OptimizationRunner()) as client:
        created = _create(client).json()
        failed = _wait_for_terminal(client, created["id"])

    assert failed["state"] == "failed"
    assert failed["error"] == {
        "code": "no_solution_found",
        "message": "No schedule was produced. Solver status: UNKNOWN",
    }


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


def test_worker_survives_when_failure_persistence_also_fails(monkeypatch):
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
            self.next_claim_attempted = threading.Event()

        def claim_next_job(self, _worker_id):
            self.claim_calls += 1
            if self.claim_calls == 1:
                return job
            self.next_claim_attempted.set()
            return None

        def get_input(self, _job_id):
            raise ConnectionError("store unavailable")

        def fail_job(self, _job_id, _failure):
            raise ConnectionError("store still unavailable")

    controller = FailingController()
    monkeypatch.setattr("nurse_scheduling.server.jobs.worker.capture_optimize_exception", lambda *_args: None)
    worker = JobWorker(
        controller,
        SuccessfulRunner(),
        worker_id="worker",
        claim_poll_seconds=0.005,
        claim_lease_seconds=60,
    )

    worker.start()
    try:
        assert controller.next_claim_attempted.wait(timeout=1)
        assert worker.is_alive()
    finally:
        worker.stop()


def test_cancel_queued_job_is_immediately_terminal():
    with _client(start_background=False) as client:
        created = _create(client).json()
        response = client.post(f"/optimize/{created['id']}/cancel")

        assert response.status_code == 202
        assert response.json()["state"] == "cancelled"
        assert response.json()["error"]["code"] == "cancelled"


@pytest.mark.parametrize(
    "solver",
    [
        "ortools/cp-sat",
        "ortools/mpsolver/scip",
        "ortools/mpsolver/cp-sat",
        "ortools/mpsolver/bop",
        "ortools/mathopt/cp-sat",
        " ORTOOLS/MPSOLVER/SCIP ",
        " ORTOOLS/MATHOPT/CP-SAT ",
    ],
)
def test_solver_supports_running_job_stop(solver):
    assert solver_supports_stop(solver)


@pytest.mark.parametrize(
    "solver",
    [
        "pulp/cbc",
        "pulp/cuopt",
        "pulp/glpk",
        "pulp/highs",
        "pulp/scip",
        "ortools/mpsolver/cbc",
        "ortools/mathopt/gscip",
        "ortools/mathopt/highs",
    ],
)
def test_solver_does_not_support_running_job_stop(solver):
    assert not solver_supports_stop(solver)


def test_cancel_running_job_stops_worker_and_discards_result():
    runner = StoppableRunner()
    with _client(runner) as client:
        created = _create(client).json()
        assert runner.started.wait(timeout=2)
        response = client.post(f"/optimize/{created['id']}/cancel")
        assert response.status_code == 202
        assert response.json()["state"] in {"cancelling", "cancelled"}

        cancelled = _wait_for_terminal(client, created["id"])
        assert cancelled["state"] == "cancelled"
        assert cancelled["result"] is None


def test_cancel_running_job_treats_solver_exception_as_cancellation(monkeypatch, caplog):
    class FailingAfterStopRunner:
        def __init__(self):
            self.started = threading.Event()

        def run(self, job, input_bytes, *, event_callback, should_stop):
            self.started.set()
            while should_stop is not None and not should_stop():
                time.sleep(0.005)
            raise ValueError("No solution found! Status: UNKNOWN")

    runner = FailingAfterStopRunner()
    captured = []
    monkeypatch.setattr(
        "nurse_scheduling.server.jobs.worker.capture_optimize_exception",
        lambda *args: captured.append(args),
    )

    with _client(runner) as client:
        created = _create(client, solver="ortools/mathopt/cp-sat").json()
        assert runner.started.wait(timeout=2)
        response = client.post(f"/optimize/{created['id']}/cancel")
        assert response.status_code == 202

        cancelled = _wait_for_terminal(client, created["id"])

    assert cancelled["state"] == "cancelled"
    assert cancelled["error"] == {
        "code": "cancelled",
        "message": "Optimization cancelled.",
    }
    assert captured == []
    assert any(
        f"[server:worker] cancelled-after-exception job_id={created['id']} "
        "exception_type=ValueError error=No solution found! Status: UNKNOWN worker_id=" in message
        for message in caplog.messages
    )


def test_finish_now_completes_with_current_feasible_result():
    runner = StoppableRunner()
    with _client(runner) as client:
        created = _create(client).json()
        assert runner.started.wait(timeout=2)
        response = client.post(f"/optimize/{created['id']}/finish-now")
        assert response.status_code == 202
        assert response.json()["controls"]["early_completion_available"] is False

        completed = _wait_for_terminal(client, created["id"])
        assert completed["state"] == "completed"
        assert completed["result"]["outcome"] == "feasible"


def test_worker_renews_claim_during_long_running_job():
    now = [datetime.now(timezone.utc)]
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        claim_lease_seconds=0.06,
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

    class ControllerWithRenewalSignal:
        def __init__(self, delegate):
            self.delegate = delegate
            self.renewal_allowed = threading.Event()
            self.claim_renewed = threading.Event()
            self.renewed_job = None

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def renew_claim(self, job_id, worker_id):
            self.renewal_allowed.wait(timeout=2)
            renewed = self.delegate.renew_claim(job_id, worker_id)
            if renewed is not None:
                self.renewed_job = renewed
                self.claim_renewed.set()
            return renewed

    worker_controller = ControllerWithRenewalSignal(controller)
    runner = StoppableRunner()
    worker = JobWorker(
        worker_controller,
        runner,
        worker_id="worker",
        claim_poll_seconds=0.005,
        claim_lease_seconds=0.06,
    )

    worker.start()
    try:
        assert runner.started.wait(timeout=2)
        initial_claim = controller.get_job(created.id)
        now[0] += timedelta(seconds=0.01)
        worker_controller.renewal_allowed.set()
        assert worker_controller.claim_renewed.wait(timeout=2)
        assert worker_controller.renewed_job.claim_expires_at > initial_claim.claim_expires_at

        running = controller.get_job(created.id)
        assert running.state == JobState.RUNNING
        controller.request_early_completion(created.id)
        assert runner.finished.wait(timeout=2)
        assert controller.get_job(created.id).state == JobState.COMPLETED
    finally:
        worker.stop()


def test_worker_stops_execution_after_its_claim_expires():
    now = [datetime.now(timezone.utc)]
    store = MemoryJobStore()
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        claim_lease_seconds=30,
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

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def is_stop_requested(self, job_id, worker_id):
            if not self.stop_read_failed.is_set():
                self.stop_read_failed.set()
                raise ConnectionError("store temporarily unavailable")
            return self.delegate.is_stop_requested(job_id, worker_id)

    worker_controller = ControllerWithTransientStopReadFailure(controller)
    runner = StoppableRunner()
    worker = JobWorker(
        worker_controller,
        runner,
        worker_id="worker",
        claim_poll_seconds=0.005,
        claim_lease_seconds=30,
    )

    worker.start()
    try:
        assert runner.started.wait(timeout=2)
        assert worker_controller.stop_read_failed.wait(timeout=2)
        now[0] += timedelta(seconds=31)
        assert controller.expire_worker_claims() == [created.id]
        assert runner.finished.wait(timeout=2)

        failed = controller.get_job(created.id)
        assert failed.state == JobState.FAILED
        assert failed.failure is not None
        assert failed.failure.code == "worker_lost"
        assert worker.is_alive()
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
