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
from pathlib import Path

import httpx

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

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal info_calls
        if request.url.path == "/info":
            with lock:
                info_calls += 1
                call = info_calls
            if call > 1:
                info_barrier.wait(timeout=1)
            return httpx.Response(
                200,
                headers={"Cache-Control": "no-store"},
                json={"status": "ready", **QueueApi._identity(call)},
            )
        if request.url.path.startswith("/optimize/"):
            snapshot_barrier.wait(timeout=1)
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1], "state": "running"})
        return httpx.Response(404)

    diagnostic = PublicDiagnostic(
        _config(scenario, tmp_path, info_samples=4, parallel_requests=3),
        transport=httpx.MockTransport(handler),
    )

    assert diagnostic._collect_info()
    diagnostic.jobs = [DiagnosticJob(id=f"job-{index}", input_name="parallel.yaml") for index in range(3)]
    snapshots = diagnostic._snapshot_jobs()

    assert info_calls == 4
    assert set(snapshots) == {"job-0", "job-1", "job-2"}
    assert diagnostic.max_running == 3


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
