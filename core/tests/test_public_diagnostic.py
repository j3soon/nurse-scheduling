"""Tests for the bounded public backend diagnostic workflow."""

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

import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from nurse_scheduling.server import diagnostic as diagnostic_module
from nurse_scheduling.server.diagnostic import (
    DiagnosticConfig,
    DiagnosticJob,
    PublicDiagnostic,
    exit_code,
    format_phase_timings,
    format_summary,
    write_report,
)


class QueueApi:
    """Small stateful HTTP transport modeling three shared Redis workers."""

    def __init__(self, concurrency: int = 3):
        self.info_index = 0
        self.jobs: dict[str, str] = {}
        self.accepted_by: dict[str, dict[str, str]] = {}
        self.run_by: dict[str, dict[str, str]] = {}
        self.worker_ids: dict[str, str] = {}
        self.score_stream_jobs: set[str] = set()
        self.cancelled_with_score: list[bool] = []
        self.controls: list[tuple[str, str]] = []
        self.concurrency = concurrency

    @staticmethod
    def _identity(instance: int) -> dict[str, str]:
        return {
            "service_name": "nurse-scheduling-api",
            "api_version": "alpha",
            "app_version": "v-test",
            "deployment_id": "deployment-test",
            "instance_id": f"instance-{instance}",
            "started_at": "2026-07-18T00:00:00+00:00",
            "job_backend": "redis",
            "job_store_id": "production-primary",
        }

    def _promote_one(self, runner: dict[str, str], worker_id: str) -> None:
        for job_id, state in self.jobs.items():
            if state == "queued":
                self.jobs[job_id] = "running"
                self.run_by[job_id] = runner
                self.worker_ids[job_id] = worker_id
                return

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/info":
            instance = self.info_index % self.concurrency + 1
            self.info_index += 1
            return httpx.Response(
                200,
                headers={"Cache-Control": "no-store"},
                json={"status": "ready", **self._identity(instance)},
            )
        if request.method == "POST" and path == "/optimize":
            job_id = f"job-{len(self.jobs) + 1}"
            running = sum(state == "running" for state in self.jobs.values())
            state = "running" if running < self.concurrency else "queued"
            self.jobs[job_id] = state
            accepted_instance = (len(self.jobs) - 1) % self.concurrency + 1
            self.accepted_by[job_id] = self._identity(accepted_instance)
            if state == "running":
                runner_instance = running + 1
                self.run_by[job_id] = self._identity(runner_instance)
                self.worker_ids[job_id] = f"worker-{runner_instance}"
            return httpx.Response(202, json={"id": job_id, "state": state})
        if path.startswith("/optimize/"):
            parts = path.strip("/").split("/")
            job_id = parts[1]
            state = self.jobs.get(job_id)
            if state is None:
                return httpx.Response(404, json={"error": {"code": "job_not_found"}})
            if request.method == "GET" and len(parts) == 2:
                return httpx.Response(200, json={"id": job_id, "state": state})
            if request.method == "GET" and parts[2] == "events":
                frames = [
                    "id: 1\nevent: job.state_changed\ndata: "
                    + json.dumps({"state": "queued", "runtime": self.accepted_by[job_id]})
                    + "\n\n"
                ]
                if job_id in self.run_by:
                    self.score_stream_jobs.add(job_id)
                    frames.extend(
                        [
                            "id: 2\nevent: job.state_changed\ndata: "
                            + json.dumps(
                                {
                                    "state": "running",
                                    "runtime": self.run_by[job_id],
                                    "worker_id": self.worker_ids[job_id],
                                }
                            )
                            + "\n\n",
                            'id: 3\nevent: job.progressed\ndata: {"score": 42}\n\n',
                        ]
                    )
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream"},
                    text="".join(frames),
                )
            if request.method == "POST" and parts[2] == "finish-now":
                self.controls.append(("finish-now", job_id))
                self.jobs[job_id] = "completed"
                if state == "running":
                    self._promote_one(self.run_by[job_id], self.worker_ids[job_id])
                return httpx.Response(202, json={"id": job_id, "state": "completed"})
            if request.method == "POST" and parts[2] == "cancel":
                self.cancelled_with_score.append(job_id in self.score_stream_jobs)
                self.controls.append(("cancel", job_id))
                self.jobs[job_id] = "cancelled"
                if state == "running":
                    self._promote_one(self.run_by[job_id], self.worker_ids[job_id])
                return httpx.Response(202, json={"id": job_id, "state": "cancelled"})
            if request.method == "DELETE" and len(parts) == 2:
                if state not in {"completed", "cancelled", "failed"}:
                    return httpx.Response(409)
                del self.jobs[job_id]
                return httpx.Response(204)
        return httpx.Response(404)


def _config(scenario: Path, report_dir: Path, **updates) -> DiagnosticConfig:
    values = {
        "target_url": "https://backend.example.test",
        "scenario_path": scenario,
        "report_dir": report_dir,
        "info_samples": 3,
        "parallel_requests": 3,
        "expected_concurrency": 3,
        "max_jobs": 8,
        "queue_stable_seconds": 0.002,
        "startup_timeout_seconds": 0.2,
        "workflow_timeout_seconds": 2.0,
        "incumbent_timeout_seconds": 0.2,
        "cleanup_timeout_seconds": 0.5,
        "request_timeout_seconds": 0.2,
        "job_timeout_seconds": 30,
        "poll_seconds": 0.001,
        "submit_interval_seconds": 0.001,
    }
    values.update(updates)
    return DiagnosticConfig(**values)


def _diagnostic(tmp_path, handler=None, **updates) -> PublicDiagnostic:
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    transport = httpx.MockTransport(handler) if handler is not None else None
    return PublicDiagnostic(_config(scenario, tmp_path, **updates), transport=transport)


def test_public_diagnostic_defaults_cover_long_batched_workflow():
    config = DiagnosticConfig()

    assert config.info_samples == 100
    assert config.parallel_requests == 10
    assert config.workflow_timeout_seconds == 600
    assert config.job_timeout_seconds == 60 * 60


def test_public_diagnostic_exercises_queue_and_cleans_up(tmp_path, capsys):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    api = QueueApi()
    diagnostic = PublicDiagnostic(
        _config(scenario, tmp_path),
        transport=httpx.MockTransport(api),
    )

    report = diagnostic.run()

    assert report["summary"] == {
        "outcome": "pass",
        "target": "https://backend.example.test",
        "job_type": "scenario",
        "job_backend": "redis",
        "versions": 1,
        "deployments": 1,
        "instances": 3,
        "runners": 3,
        "stores": 1,
        "maxRunning": 3,
        "queueTransition": "pass",
        "cleanup": "pass",
        "durationSeconds": report["summary"]["durationSeconds"],
    }
    assert report["findings"] == []
    assert report["details"]["submittedJobs"] == 8
    assert report["details"]["batchSizes"] == [3, 2]
    assert set(report["details"]["phaseDurationsSeconds"]) == {
        "readiness",
        "info_sampling",
        "info_analysis",
        "queue_saturation",
        "queue_transition",
        "identity_analysis",
        "cleanup",
    }
    assert all(value >= 0 for value in report["details"]["phaseDurationsSeconds"].values())
    assert report["details"]["acceptedHttpWorkers"]["observedJobs"] == 8
    assert len(report["details"]["acceptedHttpWorkers"]["distinctIdentities"]) == 3
    assert report["details"]["runners"]["observedJobs"] == 8
    assert len(report["details"]["runners"]["distinctIdentities"]) == 3
    assert all(job["deleted"] for job in report["details"]["jobs"])
    assert api.controls == [
        ("cancel", "job-1"),
        ("finish-now", "job-2"),
        ("finish-now", "job-3"),
        ("finish-now", "job-4"),
        ("finish-now", "job-5"),
        ("finish-now", "job-6"),
        ("finish-now", "job-7"),
        ("finish-now", "job-8"),
    ]
    assert api.cancelled_with_score == [True]
    assert api.jobs == {}
    assert exit_code(report) == 0
    assert format_summary(report).startswith(
        "PASS target=https://backend.example.test job_type=scenario "
        "job_backend=redis versions=1 deployments=1 instances=3 runners=3 stores=1 maxRunning=3"
    )
    assert format_phase_timings(report).startswith("TIMING readiness=")
    assert capsys.readouterr().out == ("CONNECTED target=https://backend.example.test http_status=200 status=ready\n")

    report_path = write_report(report, tmp_path)
    assert report_path.read_text(encoding="utf-8").endswith("\n")


def test_info_samples_and_job_snapshots_use_bounded_parallel_requests(tmp_path):
    scenario = tmp_path / "parallel.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    lock = threading.Lock()
    info_barrier = threading.Barrier(3)
    snapshot_barrier = threading.Barrier(3)
    info_calls = 0
    active = {"info": 0, "snapshot": 0}
    peak_active = {"info": 0, "snapshot": 0}

    def synchronize(kind: str, barrier: threading.Barrier) -> None:
        with lock:
            active[kind] += 1
            peak_active[kind] = max(peak_active[kind], active[kind])
        try:
            barrier.wait(timeout=1)
            time.sleep(0.01)
        finally:
            with lock:
                active[kind] -= 1

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal info_calls
        if request.url.path == "/info":
            with lock:
                info_calls += 1
                call = info_calls
            if call > 1:
                synchronize("info", info_barrier)
            return httpx.Response(
                200,
                headers={"Cache-Control": "no-store"},
                json={"status": "ready", **QueueApi._identity(call)},
            )
        if request.url.path.startswith("/optimize/"):
            synchronize("snapshot", snapshot_barrier)
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1], "state": "running"})
        return httpx.Response(404)

    diagnostic = PublicDiagnostic(
        _config(scenario, tmp_path, info_samples=7, parallel_requests=3),
        transport=httpx.MockTransport(handler),
    )

    assert diagnostic._collect_info()
    diagnostic.jobs = [DiagnosticJob(id=f"job-{index}", input_name="parallel.yaml") for index in range(6)]
    snapshots = diagnostic._snapshot_jobs()

    assert info_calls == 7
    assert set(snapshots) == {f"job-{index}" for index in range(6)}
    assert diagnostic.max_running == 6
    assert peak_active == {"info": 3, "snapshot": 3}


def test_request_batches_stop_at_workflow_deadline(tmp_path, monkeypatch):
    diagnostic = _diagnostic(tmp_path, info_samples=6, parallel_requests=3)
    release = threading.Event()
    completed = threading.Event()
    started = threading.Barrier(3)
    lock = threading.Lock()
    timeouts: list[float] = []
    completed_count = 0

    def sample_info(*, timeout_seconds: float | None = None):
        nonlocal completed_count
        assert timeout_seconds is not None
        with lock:
            timeouts.append(timeout_seconds)
        started.wait(timeout=1)
        release.wait(timeout=1)
        with lock:
            completed_count += 1
            if completed_count == 3:
                completed.set()
        return {"statusCode": 200, "body": {"status": "ready"}, "cacheControl": "no-store"}

    monkeypatch.setattr(diagnostic, "_sample_info", sample_info)
    diagnostic.workflow_deadline = time.monotonic() + 0.1

    started_at = time.monotonic()
    try:
        samples = diagnostic._sample_info_concurrently(6)
    finally:
        release.set()
    elapsed = time.monotonic() - started_at

    assert samples == []
    assert elapsed < 0.5
    assert len(timeouts) == 3
    assert all(0 < timeout <= 0.1 for timeout in timeouts)
    assert completed.wait(timeout=1)


def test_main_runs_without_creating_process_lock(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    config = _config(scenario, tmp_path)
    report = {"summary": {"outcome": "pass"}}
    runner = Mock()
    runner.run.return_value = report
    diagnostic_class = Mock(return_value=runner)
    report_path = tmp_path / "report.json"

    monkeypatch.setattr(diagnostic_module.DiagnosticConfig, "from_env", Mock(return_value=config))
    monkeypatch.setattr(diagnostic_module, "PublicDiagnostic", diagnostic_class)
    monkeypatch.setattr(diagnostic_module, "write_report", Mock(return_value=report_path))
    monkeypatch.setattr(diagnostic_module, "print_report", Mock())

    assert diagnostic_module.main([]) == 0
    assert not (tmp_path / ".diagnostic.lock").exists()
    runner.run.assert_called_once_with()


def test_job_events_expand_identity_beyond_info_routing(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    api = QueueApi()

    report = PublicDiagnostic(
        _config(scenario, tmp_path, info_samples=1),
        transport=httpx.MockTransport(api),
    ).run()

    assert report["summary"]["outcome"] == "pass"
    assert report["summary"]["instances"] == 3
    assert report["summary"]["runners"] == 3
    assert len(report["details"]["infoSampling"]["distinctReturns"]) == 1
    assert len(report["details"]["acceptedHttpWorkers"]["distinctIdentities"]) == 3
    assert len(report["details"]["runners"]["distinctIdentities"]) == 3


def test_startup_retries_are_separate_from_ready_info_samples(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    api = QueueApi()
    startup_failures = 2

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal startup_failures
        if request.method == "GET" and request.url.path == "/info" and startup_failures:
            startup_failures -= 1
            return httpx.Response(
                503,
                headers={"Cache-Control": "no-store"},
                json={
                    "status": "unavailable",
                    "service_name": "nurse-scheduling-api",
                    "api_version": "alpha",
                    "app_version": "v-test",
                    "deployment_id": "deployment-test",
                    "instance_id": "instance-1",
                    "started_at": "2026-07-18T00:00:00+00:00",
                    "job_backend": "redis",
                    "job_store_id": "production-primary",
                    "reason": "job_worker_unavailable",
                },
            )
        return api(request)

    report = PublicDiagnostic(
        _config(scenario, tmp_path),
        transport=httpx.MockTransport(handler),
    ).run()

    assert report["summary"]["outcome"] == "pass"
    assert report["details"]["startupSampling"] == {
        "attempts": 2,
        "distinctReturns": [
            {
                "count": 2,
                "statusCode": 503,
                "body": {
                    "status": "unavailable",
                    "service_name": "nurse-scheduling-api",
                    "api_version": "alpha",
                    "app_version": "v-test",
                    "deployment_id": "deployment-test",
                    "instance_id": "instance-1",
                    "started_at": "2026-07-18T00:00:00+00:00",
                    "job_backend": "redis",
                    "job_store_id": "production-primary",
                    "reason": "job_worker_unavailable",
                },
                "cacheControl": "no-store",
            }
        ],
    }
    assert report["details"]["infoSampling"]["collected"] == 3
    assert len(report["details"]["infoSampling"]["distinctReturns"]) == 3


def test_info_sampling_reports_mixed_backends_and_stores(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/info":
            calls += 1
            backend = "memory" if calls % 2 else "redis"
            return httpx.Response(
                200,
                headers={"Cache-Control": "no-store"},
                json={
                    "status": "ready",
                    "service_name": "nurse-scheduling-api",
                    "api_version": "alpha",
                    "app_version": "v-test",
                    "deployment_id": "deployment-test",
                    "instance_id": f"instance-{calls}",
                    "started_at": "2026-07-18T00:00:00+00:00",
                    "job_backend": backend,
                    "job_store_id": f"{backend}-store",
                },
            )
        if request.url.path == "/optimize":
            return httpx.Response(429)
        return httpx.Response(404)

    report = PublicDiagnostic(
        _config(scenario, tmp_path, expected_concurrency=1),
        transport=httpx.MockTransport(handler),
    ).run()

    codes = {finding["code"] for finding in report["findings"]}
    assert report["summary"]["outcome"] == "fail"
    assert report["summary"]["job_backend"] == "mixed"
    assert report["summary"]["stores"] == 2
    assert "mixed_job_backends" in codes
    assert "mixed_job_stores" in codes
    assert exit_code(report) == 1


def test_public_diagnostic_stops_submitting_after_known_job_is_missing(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    submissions = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submissions
        if request.method == "GET" and request.url.path == "/info":
            return httpx.Response(
                200,
                headers={"Cache-Control": "no-store"},
                json={
                    "status": "ready",
                    "service_name": "nurse-scheduling-api",
                    "api_version": "alpha",
                    "app_version": "v-test",
                    "deployment_id": "deployment-test",
                    "instance_id": "instance-1",
                    "started_at": "2026-07-18T00:00:00+00:00",
                    "job_backend": "redis",
                    "job_store_id": "production-primary",
                },
            )
        if request.method == "POST" and request.url.path == "/optimize":
            submissions += 1
            return httpx.Response(202, json={"id": f"job-{submissions}", "state": "running"})
        if request.method == "GET" and request.url.path.startswith("/optimize/"):
            return httpx.Response(404)
        return httpx.Response(404)

    report = PublicDiagnostic(
        _config(
            scenario,
            tmp_path,
            info_samples=1,
            expected_concurrency=1,
            cleanup_timeout_seconds=0.01,
        ),
        transport=httpx.MockTransport(handler),
    ).run()

    assert submissions == 1
    assert report["summary"]["outcome"] == "fail"
    assert "job_visibility_split" in {finding["code"] for finding in report["findings"]}


def test_public_diagnostic_adapts_queue_release_to_one_worker(tmp_path):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    api = QueueApi(concurrency=1)

    report = PublicDiagnostic(
        _config(scenario, tmp_path, info_samples=1, expected_concurrency=1),
        transport=httpx.MockTransport(api),
    ).run()

    assert report["summary"]["outcome"] == "pass"
    assert report["summary"]["maxRunning"] == 1
    assert report["summary"]["queueTransition"] == "pass"
    assert report["details"]["submittedJobs"] == 6
    assert report["details"]["batchSizes"] == [1, 1, 1, 1, 1]
    assert api.controls == [
        ("cancel", "job-1"),
        ("finish-now", "job-2"),
        ("finish-now", "job-3"),
        ("finish-now", "job-4"),
        ("finish-now", "job-5"),
        ("finish-now", "job-6"),
    ]
    assert api.jobs == {}


def test_diagnostic_config_loads_environment_and_rejects_invalid_numbers(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")
    monkeypatch.setenv("DIAGNOSTIC_INFO_SAMPLES", "4")
    monkeypatch.setenv("DIAGNOSTIC_QUEUE_STABLE_SECONDS", "0.25")

    config = DiagnosticConfig.from_env(
        target_url="https://backend.example.test/",
        scenario_path=scenario,
        report_dir=tmp_path,
    )

    assert config.target_url == "https://backend.example.test"
    assert config.info_samples == 4
    assert config.queue_stable_seconds == 0.25

    monkeypatch.setenv("DIAGNOSTIC_INFO_SAMPLES", "0")
    with pytest.raises(ValueError, match="positive integer"):
        DiagnosticConfig.from_env(scenario_path=scenario)

    monkeypatch.setenv("DIAGNOSTIC_INFO_SAMPLES", "4")
    monkeypatch.setenv("DIAGNOSTIC_QUEUE_STABLE_SECONDS", "nan")
    with pytest.raises(ValueError, match="positive number"):
        DiagnosticConfig.from_env(scenario_path=scenario)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"target_url": "backend.example.test"}, "absolute HTTP"),
        ({"target_url": "https://user:secret@backend.example.test"}, "credentials"),
        ({"target_url": "https://backend.example.test/info"}, "path, query, or fragment"),
        ({"info_samples": 0}, "info_samples must be positive"),
        ({"queue_stable_seconds": float("nan")}, "queue_stable_seconds must be positive"),
    ],
)
def test_diagnostic_config_rejects_invalid_settings(tmp_path, updates, message):
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("apiVersion: alpha\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _config(scenario, tmp_path, **updates)


def test_diagnostic_config_rejects_missing_scenario(tmp_path):
    with pytest.raises(ValueError, match="scenario was not found"):
        DiagnosticConfig(scenario_path=tmp_path / "missing.yaml")


def test_analysis_reports_invalid_info_and_runtime_identities(tmp_path):
    diagnostic = _diagnostic(tmp_path, expected_concurrency=2, info_samples=3)
    first = {
        **QueueApi._identity(1),
        "service_name": "unexpected-api",
        "api_version": "v1",
        "app_version": "app-v1",
        "deployment_id": "unmanaged",
        "job_backend": "memory",
        "job_store_id": "unconfigured",
    }
    second = {
        **QueueApi._identity(2),
        "api_version": "v2",
        "app_version": "app-v2",
        "deployment_id": "deployment-two",
        "job_backend": "redis",
        "job_store_id": "store-two",
    }
    third = {**QueueApi._identity(3), "job_backend": "memory"}
    diagnostic.startup_attempts = [
        {"statusCode": 404, "body": {"status": ""}, "cacheControl": "public"},
    ]
    diagnostic.info_samples = [
        {"statusCode": 503, "body": first, "cacheControl": "no-store"},
        {"statusCode": 200, "body": second, "cacheControl": "no-store"},
    ]
    diagnostic.accepted_http_workers = [third, {}]
    diagnostic.runners = [{"worker_id": ""}]
    diagnostic.jobs = [
        DiagnosticJob(id="unchecked", input_name="scenario.yaml"),
        DiagnosticJob(id="missing", input_name="scenario.yaml", transitions=["queued", "running"]),
    ]
    diagnostic.event_jobs_checked.add("missing")

    diagnostic._analyze_info()
    diagnostic._analyze_runtime_identities()

    codes = {finding.code for finding in diagnostic.findings}
    assert {
        "info_endpoint_missing",
        "incomplete_info",
        "empty_info_identity",
        "info_cache_control",
        "intermittent_readiness",
        "info_sampling_incomplete",
        "incomplete_event_identity",
        "empty_event_identity",
        "job_identity_not_checked",
        "accepted_identity_missing",
        "runner_identity_missing",
        "unexpected_service_identity",
        "mixed_api_versions",
        "mixed_app_versions",
        "mixed_deployments",
        "unmanaged_deployment",
        "mixed_job_backends",
        "mixed_job_stores",
        "unconfigured_job_store",
        "memory_with_multiple_workers",
        "split_memory_instances",
        "unexpected_instance_count",
    } <= codes


def test_info_helpers_handle_transport_and_payload_edge_cases(tmp_path, capsys, monkeypatch):
    def fail_info(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("backend unavailable", request=request)

    diagnostic = _diagnostic(tmp_path, fail_info, parallel_requests=1)

    assert diagnostic._sample_info()["statusCode"] is None
    assert diagnostic._sample_info_concurrently(0) == []

    sample = {"statusCode": 200, "body": {"status": "ready"}, "cacheControl": "no-store"}
    sample_info = Mock(return_value=sample)
    monkeypatch.setattr(diagnostic, "_sample_info", sample_info)
    assert diagnostic._sample_info_concurrently(2) == [sample, sample]
    assert sample_info.call_count == 2

    assert diagnostic._json_object(httpx.Response(200, text="not-json")) is None
    identity = QueueApi._identity(1)
    diagnostic._observe_event_identity("job", "1", {"state": "queued", "runtime": identity})
    diagnostic._observe_event_identity("job", "1", {"state": "queued", "runtime": identity})
    assert diagnostic.accepted_http_workers == [identity]

    diagnostic._announce_connection({"statusCode": 200, "body": []})
    diagnostic._announce_connection(sample)
    assert "status=unknown" in capsys.readouterr().out


def test_job_submission_and_reads_report_error_responses(tmp_path, monkeypatch):
    responses = [
        httpx.Response(429),
        httpx.Response(500, text="server error"),
        httpx.Response(202, json=[]),
    ]

    def submit_handler(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    diagnostic = _diagnostic(tmp_path, submit_handler)
    assert diagnostic._create_job(1) is None
    assert diagnostic._create_job(2) is None
    assert diagnostic._create_job(3) is None

    monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=OSError("scenario unavailable")))
    assert diagnostic._create_job(4) is None

    codes = {finding.code for finding in diagnostic.findings}
    assert {"job_capacity_reached", "job_submission_error", "invalid_job_response"} <= codes

    read_responses = [
        httpx.Response(500, text="server error"),
        httpx.Response(200, text="not-json"),
    ]

    def read_handler(request: httpx.Request) -> httpx.Response:
        if read_responses:
            return read_responses.pop(0)
        raise httpx.ConnectError("read failed", request=request)

    reader = _diagnostic(tmp_path, read_handler, parallel_requests=1)
    reader.jobs = [DiagnosticJob(id="job", input_name="scenario.yaml")]
    assert reader._get_job("job") is None
    assert reader._get_job("job") is None
    assert reader._get_job("job") is None
    assert reader._get_jobs([]) == {}

    monkeypatch.setattr(reader, "_get_job", Mock(return_value={"state": "queued"}))
    assert reader._get_jobs(["job"]) == {"job": {"state": "queued"}}


def test_event_replay_and_controls_report_transport_errors(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        job_id = request.url.path.split("/")[2]
        if request.method == "GET":
            if job_id == "bad-status":
                return httpx.Response(500)
            if job_id == "invalid-event":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream"},
                    text="event: job.progressed\ndata: {\n\n",
                )
            if job_id == "timeout":
                raise httpx.ReadTimeout("stream timeout", request=request)
            raise httpx.ConnectError("stream failed", request=request)
        if job_id == "control-error":
            raise httpx.ConnectError("control failed", request=request)
        if job_id == "control-missing":
            return httpx.Response(404)
        return httpx.Response(500, text="control rejected")

    diagnostic = _diagnostic(tmp_path, handler)

    assert not diagnostic._replay_job_events("bad-status", stop_on_score=True, read_seconds=0.1)
    assert not diagnostic._replay_job_events("invalid-event", stop_on_score=True, read_seconds=0.1)
    assert not diagnostic._replay_job_events("timeout", stop_on_score=True, read_seconds=0.1)
    assert not diagnostic._replay_job_events("stream-error", stop_on_score=True, read_seconds=0.1)
    assert not diagnostic._post_control("control-error", "cancel")
    assert not diagnostic._post_control("control-missing", "cancel")
    diagnostic.visibility_split = False
    assert not diagnostic._post_control("control-rejected", "cancel")

    assert diagnostic.visibility_split is False
    assert len(diagnostic.request_errors) == 4


def test_wait_and_finish_helpers_cover_incomplete_transitions(tmp_path, monkeypatch):
    diagnostic = _diagnostic(tmp_path)
    diagnostic.visibility_split = True
    monkeypatch.setattr(diagnostic, "_get_jobs", Mock(return_value={}))
    assert diagnostic._wait_for_terminal(["job"], 0.1) == {}

    diagnostic.visibility_split = False
    diagnostic.workflow_deadline = time.monotonic() + 1
    assert not diagnostic._wait_for_running(["job"], 0.1)

    diagnostic.workflow_deadline = time.monotonic() + 1
    diagnostic._get_jobs.return_value = {"job": {"state": "failed"}}
    assert not diagnostic._wait_for_running(["job"], 0.1)

    diagnostic.workflow_deadline = time.monotonic() - 1
    assert diagnostic._wait_for_terminal(["job"], 0.1) == {}
    assert not diagnostic._wait_for_running(["job"], 0.1)

    assert diagnostic._finish_running_jobs([])
    monkeypatch.setattr(diagnostic, "_select_jobs_with_incumbents", Mock(return_value=[]))
    assert not diagnostic._finish_running_jobs(["job"])

    diagnostic._select_jobs_with_incumbents.return_value = ["job"]
    monkeypatch.setattr(diagnostic, "_post_control", Mock(return_value=False))
    assert not diagnostic._finish_running_jobs(["job"])

    diagnostic._post_control.return_value = True
    monkeypatch.setattr(diagnostic, "_wait_for_terminal", Mock(return_value={}))
    assert not diagnostic._finish_running_jobs(["job"])

    diagnostic._wait_for_terminal.return_value = {"job": {"state": "failed"}}
    assert not diagnostic._finish_running_jobs(["job"])
    assert diagnostic.queue_transition == "fail"


def test_incomplete_job_snapshots_are_retried(tmp_path, monkeypatch):
    diagnostic = _diagnostic(tmp_path)
    jobs = [
        DiagnosticJob(id="job-1", input_name="scenario.yaml"),
        DiagnosticJob(id="job-2", input_name="scenario.yaml"),
    ]
    diagnostic.jobs = jobs
    calls = 0

    def get_jobs(job_ids: list[str]) -> dict[str, dict[str, str]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {job_ids[0]: {"state": "queued"}}
        return {job_id: {"state": "queued"} for job_id in job_ids}

    monkeypatch.setattr(diagnostic, "_get_jobs", get_jobs)

    assert diagnostic._jobs_stay_queued(jobs)
    assert calls >= 3

    diagnostic.workflow_deadline = time.monotonic() + 1
    diagnostic._get_jobs = Mock(
        side_effect=[
            {"job-1": {"state": "running"}},
            {
                "job-1": {"state": "running"},
                "job-2": {"state": "running"},
            },
        ]
    )

    assert diagnostic._wait_for_running(["job-1", "job-2"], 0.1)
    assert diagnostic._get_jobs.call_count == 2


def test_queue_transition_reports_each_incomplete_control_stage(tmp_path):
    no_running = _diagnostic(tmp_path, expected_concurrency=1)
    no_running._snapshot_jobs = Mock(return_value={})
    no_running._exercise_queue_transition([])
    assert {finding.code for finding in no_running.findings} >= {
        "insufficient_running_jobs",
        "no_running_jobs",
    }

    changed = _diagnostic(tmp_path, expected_concurrency=2)
    changed.max_running = 2
    changed._snapshot_jobs = Mock(return_value={"run": {"state": "running"}})
    changed._exercise_queue_transition([])
    assert changed.findings[-1].code == "running_batch_changed"

    no_score = _diagnostic(tmp_path, expected_concurrency=1)
    no_score.max_running = 1
    no_score._snapshot_jobs = Mock(return_value={"run": {"state": "running"}})
    no_score._select_jobs_with_incumbents = Mock(return_value=[])
    no_score._exercise_queue_transition([])
    assert no_score.findings[-1].code == "incumbents_not_observed"

    control_failed = _diagnostic(tmp_path, expected_concurrency=1)
    control_failed.max_running = 1
    control_failed._snapshot_jobs = Mock(return_value={"run": {"state": "running"}})
    control_failed._select_jobs_with_incumbents = Mock(return_value=["run"])
    control_failed._post_control = Mock(return_value=False)
    control_failed._exercise_queue_transition([])
    assert control_failed.queue_transition == "fail"

    release_timeout = _diagnostic(tmp_path, expected_concurrency=1)
    release_timeout.max_running = 1
    release_timeout._snapshot_jobs = Mock(return_value={"run": {"state": "running"}})
    release_timeout._select_jobs_with_incumbents = Mock(return_value=["run"])
    release_timeout._post_control = Mock(return_value=True)
    release_timeout._wait_for_terminal = Mock(return_value={})
    release_timeout._exercise_queue_transition([])
    assert release_timeout.findings[-1].code == "release_timeout"

    cancel_failed = _diagnostic(tmp_path, expected_concurrency=1)
    cancel_failed.max_running = 1
    cancel_failed._snapshot_jobs = Mock(return_value={"run": {"state": "running"}})
    cancel_failed._select_jobs_with_incumbents = Mock(return_value=["run"])
    cancel_failed._post_control = Mock(return_value=True)
    cancel_failed._wait_for_terminal = Mock(return_value={"run": {"state": "completed"}})
    cancel_failed._exercise_queue_transition([])
    assert cancel_failed.findings[-1].code == "running_cancel_failed"

    finish_failed = _diagnostic(tmp_path, expected_concurrency=2)
    finish_failed.max_running = 2
    finish_failed._snapshot_jobs = Mock(return_value={"cancel": {"state": "running"}, "finish": {"state": "running"}})
    finish_failed._select_jobs_with_incumbents = Mock(return_value=["cancel", "finish"])
    finish_failed._post_control = Mock(return_value=True)
    finish_failed._wait_for_terminal = Mock(
        return_value={"cancel": {"state": "cancelled"}, "finish": {"state": "failed"}}
    )
    finish_failed._exercise_queue_transition([])
    assert finish_failed.findings[-1].code == "finish_now_failed"

    queued_timeout = _diagnostic(tmp_path, expected_concurrency=1)
    queued_timeout.max_running = 1
    queued_timeout._snapshot_jobs = Mock(return_value={"run": {"state": "running"}})
    queued_timeout._select_jobs_with_incumbents = Mock(return_value=["run"])
    queued_timeout._post_control = Mock(return_value=True)
    queued_timeout._wait_for_terminal = Mock(return_value={"run": {"state": "cancelled"}})
    queued_timeout._wait_for_running = Mock(return_value=False)
    queued_timeout._exercise_queue_transition(["queued"])
    assert queued_timeout.findings[-1].code == "queued_jobs_did_not_run"
    assert queued_timeout.queue_transition == "inconclusive"

    active_final = _diagnostic(tmp_path, expected_concurrency=1)
    active_final.max_running = 1
    active_final._snapshot_jobs = Mock(side_effect=[{"run": {"state": "running"}}, {"queued": {"state": "running"}}])
    active_final._select_jobs_with_incumbents = Mock(return_value=["run"])
    active_final._post_control = Mock(return_value=True)
    active_final._wait_for_terminal = Mock(return_value={"run": {"state": "cancelled"}})
    active_final._wait_for_running = Mock(return_value=True)
    active_final._finish_running_jobs = Mock(return_value=True)
    active_final._exercise_queue_transition(["queued"])
    assert active_final.findings[-1].code == "diagnostic_jobs_still_active"


def test_cleanup_run_and_cli_paths_report_errors(tmp_path, monkeypatch, capsys):
    def cleanup_handler(request: httpx.Request) -> httpx.Response:
        job_id = request.url.path.split("/")[2]
        if job_id == "transport-error":
            raise httpx.ConnectError("cleanup failed", request=request)
        if request.method == "GET":
            if job_id == "missing":
                return httpx.Response(404)
            if job_id == "invalid":
                return httpx.Response(500)
            if job_id == "active":
                return httpx.Response(200, json={"state": "running"})
            return httpx.Response(200, json={"state": "completed"})
        return httpx.Response(500)

    diagnostic = _diagnostic(tmp_path, cleanup_handler)
    diagnostic.jobs = [
        DiagnosticJob(id=job_id, input_name="scenario.yaml")
        for job_id in ("missing", "invalid", "active", "terminal", "transport-error", "deadline")
    ]
    deadline = time.monotonic() + 1
    for job in diagnostic.jobs[:-1]:
        diagnostic._cleanup_one_attempt(job, deadline)
    diagnostic._cleanup_one_attempt(diagnostic.jobs[-1], time.monotonic())
    assert len(diagnostic.request_errors) == 4

    empty = _diagnostic(tmp_path)
    empty._cleanup_jobs()
    assert empty.cleanup == "pass"

    partial = _diagnostic(tmp_path, cleanup_timeout_seconds=0.001, poll_seconds=0.001)
    partial.jobs = [DiagnosticJob(id="remaining", input_name="scenario.yaml")]
    partial._cleanup_one_attempt = Mock()
    partial._cleanup_jobs()
    assert partial.cleanup == "partial"
    assert partial.findings[-1].code == "cleanup_incomplete"

    unexpected = _diagnostic(tmp_path)
    unexpected._collect_info = Mock(side_effect=RuntimeError("unexpected"))
    unexpected._analyze_runtime_identities = Mock()
    report = unexpected.run()
    assert report["summary"]["outcome"] == "inconclusive"
    assert report["summary"]["job_backend"] == "unknown"
    assert report["findings"][-1]["code"] == "unexpected_error"

    identity_failure = _diagnostic(tmp_path)
    identity_failure._collect_info = Mock(return_value=False)
    identity_failure._analyze_runtime_identities = Mock(side_effect=RuntimeError("identity failed"))
    identity_failure._cleanup_jobs = Mock()

    identity_report = identity_failure.run()

    identity_failure._cleanup_jobs.assert_called_once_with()
    assert identity_report["summary"]["outcome"] == "inconclusive"
    assert identity_report["findings"][-1]["code"] == "identity_analysis_error"
    assert identity_report["details"]["requestErrors"] == [
        "unexpected identity analysis error: RuntimeError: identity failed"
    ]

    report["findings"].append({"level": "warning", "code": "example", "message": "Example warning."})
    report_path = tmp_path / "report.json"
    diagnostic_module.print_report(report, report_path)
    output = capsys.readouterr().out
    assert "WARNING example: Example warning." in output
    assert f"report={report_path}" in output

    monkeypatch.setattr(
        diagnostic_module.DiagnosticConfig,
        "from_env",
        Mock(side_effect=ValueError("invalid configuration")),
    )
    assert diagnostic_module.main([]) == 1
    assert "FAIL configuration" in capsys.readouterr().err

    config = unexpected.config
    runner = Mock()
    runner.run.return_value = report
    monkeypatch.setattr(diagnostic_module.DiagnosticConfig, "from_env", Mock(return_value=config))
    monkeypatch.setattr(diagnostic_module, "PublicDiagnostic", Mock(return_value=runner))
    monkeypatch.setattr(diagnostic_module, "write_report", Mock(side_effect=OSError("disk full")))
    print_report = Mock()
    monkeypatch.setattr(diagnostic_module, "print_report", print_report)
    assert diagnostic_module.main([]) == 2
    assert "WARNING report_write_failed" in capsys.readouterr().err
    print_report.assert_called_once_with(report, None)
