"""Pytest tests for the nurse scheduling FastAPI server."""

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

# Based on the FastAPI Testing guide: https://fastapi.tiangolo.com/tutorial/testing/

import os
import sys
import threading
import time
import types
import uuid
from datetime import UTC, datetime, timedelta

# Add the project root to the Python path so imports will work when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ortools.sat.python import cp_model

import nurse_scheduling.serve as serve
from nurse_scheduling.solver_interface import SchedulePhaseProgress, SolverProgress
from nurse_scheduling.solver_ortools_cp_sat import ORToolsSolver
from nurse_scheduling.serve import app

# Test client
client = TestClient(app)

# Test directories
TEST_DIR = Path(__file__).parent / "testcases" / "basics"
VALID_YAML_FILE = TEST_DIR / "01_1nurse_1shift_1day.yaml"
ERROR_YAML_FILE = TEST_DIR / "01_1nurse_1shift_1day_extra_parameter_error.txt"


def wait_for_job_status(job_id: str, *statuses: str) -> dict:
    for _ in range(100):
        response = client.get(f"/optimize/{job_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in statuses:
            return data
        time.sleep(0.01)
    pytest.fail(f"Job {job_id} did not reach one of the expected statuses: {statuses}")


class TestServerHealth:
    """Test server health and basic endpoints."""

    @pytest.mark.parametrize("origin", ["http://localhost:3001", "http://127.0.0.1:5173"])
    def test_cors_allows_local_development_origin_on_arbitrary_port(self, origin):
        response = client.get("/", headers={"Origin": origin})

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin

    def test_cors_rejects_untrusted_origin(self):
        response = client.get("/", headers={"Origin": "http://localhost.evil.example:3001"})

        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_server_root(self):
        """Check if server is running and returns correct response."""
        response = client.get("/")
        assert response.status_code == 200
        json_data = response.json()
        assert "message" in json_data
        assert "version" in json_data
        assert "appVersion" in json_data
        assert json_data["message"] == "Nurse Scheduling API"
        assert json_data["version"] == "alpha"
        assert isinstance(json_data["appVersion"], str)
        assert json_data["appVersion"]

    def test_server_health(self):
        """Check if the health endpoint returns server status metadata."""
        response = client.get("/health")
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "ok"
        assert json_data["version"] == "alpha"
        assert json_data["apiVersion"] == "alpha"
        assert isinstance(json_data["appVersion"], str)
        assert json_data["appVersion"]
        assert "time" not in json_data


class TestOptimizeJobs:
    """Test asynchronous optimization job endpoints."""

    @pytest.fixture(autouse=True)
    def clear_optimize_jobs(self):
        with serve.optimize_jobs_state._optimize_jobs_lock:
            serve.optimize_jobs_state._optimize_jobs.clear()
        yield
        with serve.optimize_jobs_state._optimize_jobs_lock:
            serve.optimize_jobs_state._optimize_jobs.clear()

    @pytest.fixture
    def fake_successful_scheduler(self, monkeypatch):
        def fake_schedule(*args, **kwargs):
            return "fake_df", {}, 42, "OPTIMAL", None

        def fake_export_to_excel(df, output_buffer, cell_export_info):
            assert df == "fake_df"
            assert cell_export_info is None
            output_buffer.write(b"fake xlsx bytes")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)
        monkeypatch.setattr(serve.exporter, "export_to_excel", fake_export_to_excel)

    def test_optimize_job_lifecycle_and_xlsx_download(self, fake_successful_scheduler, caplog):
        client.cookies.clear()
        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

        assert response.status_code == 202
        assert serve.CLIENT_UUID_COOKIE_NAME in response.headers.get("set-cookie", "")
        client_uuid = client.cookies[serve.CLIENT_UUID_COOKIE_NAME]
        uuid.UUID(client_uuid)
        created = response.json()
        job_id = created["jobId"]
        assert job_id.startswith("opt_")
        assert created["status"] in {"queued", "running", "optimal"}
        assert created["timeout"] == serve.DEFAULT_OPTIMIZATION_TIMEOUT_SECONDS
        assert created["links"]["events"] == f"/optimize/{job_id}/events"
        assert created["links"]["heartbeat"] == f"/optimize/{job_id}/heartbeat"

        completed = wait_for_job_status(job_id, "optimal")
        assert completed["score"] == 42
        assert completed["solverStatus"] == "OPTIMAL"
        assert completed["xlsxReady"] is True

        download = client.get(f"/optimize/{job_id}/xlsx")
        assert download.status_code == 200
        assert download.content == b"fake xlsx bytes"
        assert download.headers["X-Schedule-Score"] == "42"
        assert download.headers["X-Schedule-Status"] == "OPTIMAL"
        assert any(
            f"[server:job] queued job_id={job_id} " in message and f"client_uuid={client_uuid}" in message
            for message in caplog.messages
        )
        assert any(
            f"[server:job] started job_id={job_id} " in message and f"client_uuid={client_uuid}" in message
            for message in caplog.messages
        )
        assert any(
            f"[server:job] completed job_id={job_id} status=optimal score=42 " in message
            and f"client_uuid={client_uuid}" in message
            for message in caplog.messages
        )

    def test_optimize_job_accepts_file_upload_and_options(self, fake_successful_scheduler):
        with open(VALID_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")},
                data={"prettify": "true", "timeout": "60", "solver": "pulp/cbc"},
            )

        assert response.status_code == 202
        created = response.json()
        assert created["inputName"] == "01_1nurse_1shift_1day.yaml"
        assert created["prettify"] is True
        assert created["timeout"] == 60
        assert created["solver"] == "pulp/cbc"

        completed = wait_for_job_status(created["jobId"], "optimal")
        assert completed["xlsxReady"] is True

    def test_optimize_job_reuses_client_uuid_cookie(self, fake_successful_scheduler):
        client.cookies.clear()
        first = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        assert first.status_code == 202
        client_uuid = client.cookies[serve.CLIENT_UUID_COOKIE_NAME]
        uuid.UUID(client_uuid)

        client.cookies.set(serve.CLIENT_UUID_COOKIE_NAME, client_uuid)
        second = client.post(
            "/optimize",
            data={"yaml_content": "apiVersion: alpha\n"},
        )

        assert second.status_code == 202
        assert serve.CLIENT_UUID_COOKIE_NAME not in second.headers.get("set-cookie", "")
        first_job = serve.optimize_job_store.get_job(first.json()["jobId"])
        second_job = serve.optimize_job_store.get_job(second.json()["jobId"])
        assert first_job.client_uuid == client_uuid
        assert second_job.client_uuid == client_uuid

    def test_optimize_job_replaces_invalid_client_uuid_cookie(self, fake_successful_scheduler):
        client.cookies.clear()
        client.cookies.set(serve.CLIENT_UUID_COOKIE_NAME, "not-a-uuid")

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

        assert response.status_code == 202
        assert serve.CLIENT_UUID_COOKIE_NAME in response.headers.get("set-cookie", "")
        client_uuid = response.cookies[serve.CLIENT_UUID_COOKIE_NAME]
        uuid.UUID(client_uuid)
        assert client_uuid != "not-a-uuid"
        job = serve.optimize_job_store.get_job(response.json()["jobId"])
        assert job.client_uuid == client_uuid

    def test_optimize_job_normalizes_client_uuid_cookie(self, fake_successful_scheduler):
        client.cookies.clear()
        client_uuid = uuid.uuid4()
        client.cookies.set(serve.CLIENT_UUID_COOKIE_NAME, str(client_uuid))

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

        assert response.status_code == 202
        assert serve.CLIENT_UUID_COOKIE_NAME not in response.headers.get("set-cookie", "")
        job = serve.optimize_job_store.get_job(response.json()["jobId"])
        assert job.client_uuid == client_uuid.hex

    def test_optimize_job_streams_lifecycle_events(self, fake_successful_scheduler):
        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        with client.stream("GET", f"/optimize/{job_id}/events") as stream_response:
            assert stream_response.status_code == 200
            body = stream_response.read().decode("utf-8")

        assert "event: status" in body
        assert '"status": "queued"' in body
        assert "event: complete" in body
        assert '"status": "optimal"' in body
        assert '"score": 42' in body

    def test_optimize_job_streams_progress_events(self, monkeypatch):
        def fake_schedule(*args, **kwargs):
            kwargs["progress_callback"](
                SolverProgress(
                    source="pulp/cbc:solver-log:incumbent",
                    currentBestScore=7,
                    elapsedSeconds=0.1,
                    cell_export_info={"comments": {(1, 2): ["a", "b"]}},
                )
            )
            return "fake_df", {}, 42, "OPTIMAL", None

        def fake_export_to_excel(df, output_buffer, cell_export_info):
            output_buffer.write(b"fake xlsx bytes")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)
        monkeypatch.setattr(serve.exporter, "export_to_excel", fake_export_to_excel)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        with client.stream("GET", f"/optimize/{job_id}/events") as stream_response:
            assert stream_response.status_code == 200
            body = stream_response.read().decode("utf-8")

        assert "event: progress" in body
        assert '"source": "pulp/cbc:solver-log:incumbent"' in body
        assert '"currentBestScore": 7' in body
        assert '"commentCount": 2' in body

    def test_optimize_job_streams_phase_events(self, monkeypatch):
        def fake_schedule(*args, **kwargs):
            kwargs["progress_callback"](
                SchedulePhaseProgress(
                    source="scheduler:phase",
                    code="loading_scenario",
                    message="Loading schedule configuration",
                    elapsedSeconds=0.001,
                )
            )
            return "fake_df", {}, 42, "OPTIMAL", None

        def fake_export_to_excel(df, output_buffer, cell_export_info):
            output_buffer.write(b"fake xlsx bytes")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)
        monkeypatch.setattr(serve.exporter, "export_to_excel", fake_export_to_excel)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        with client.stream("GET", f"/optimize/{job_id}/events") as stream_response:
            assert stream_response.status_code == 200
            body = stream_response.read().decode("utf-8")

        assert "event: phase" in body
        assert '"source": "scheduler:phase"' in body
        assert '"code": "loading_scenario"' in body
        assert '"message": "Loading schedule configuration"' in body
        assert '"progress"' not in body

    def test_optimize_job_streams_phase_before_solver_progress(self, monkeypatch):
        def fake_schedule(*args, **kwargs):
            kwargs["progress_callback"](
                SchedulePhaseProgress(
                    source="scheduler:phase",
                    code="solving",
                    message="Solving schedule",
                    elapsedSeconds=0.1,
                )
            )
            kwargs["progress_callback"](
                SolverProgress(
                    source="pulp/cbc:solver-log:incumbent",
                    currentBestScore=7,
                    elapsedSeconds=0.2,
                )
            )
            return "fake_df", {}, 42, "OPTIMAL", None

        def fake_export_to_excel(df, output_buffer, cell_export_info):
            output_buffer.write(b"fake xlsx bytes")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)
        monkeypatch.setattr(serve.exporter, "export_to_excel", fake_export_to_excel)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        with client.stream("GET", f"/optimize/{job_id}/events") as stream_response:
            assert stream_response.status_code == 200
            body = stream_response.read().decode("utf-8")

        assert body.index("event: phase") < body.index("event: progress")
        assert '"code": "solving"' in body
        assert '"currentBestScore": 7' in body

    def test_optimize_job_cancel_requests_running_job_stop(self, monkeypatch):
        solve_started = False

        def fake_schedule(*args, **kwargs):
            nonlocal solve_started
            solve_started = True
            wait_for_stop = kwargs["should_stop"]
            for _ in range(100):
                if wait_for_stop():
                    return "fake_df", {}, 7, "FEASIBLE", None
                time.sleep(0.01)
            pytest.fail("cancel request was not observed")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "running")

        cancel_response = client.post(f"/optimize/{job_id}/cancel")

        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] in {"cancelling", "cancelled"}
        completed = wait_for_job_status(job_id, "cancelled")
        assert solve_started
        assert completed["error"] == "Optimization cancelled."
        assert completed["xlsxReady"] is False

    def test_optimize_job_finish_now_requests_best_available_result(self, monkeypatch, caplog):
        def fake_schedule(*args, **kwargs):
            wait_for_stop = kwargs["should_stop"]
            for _ in range(100):
                if wait_for_stop():
                    return "fake_df", {}, 7, "FEASIBLE", None
                time.sleep(0.01)
            pytest.fail("finish-now request was not observed")

        def fake_export_to_excel(df, output_buffer, cell_export_info):
            output_buffer.write(b"fake xlsx bytes")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)
        monkeypatch.setattr(serve.exporter, "export_to_excel", fake_export_to_excel)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "running")

        finish_response = client.post(f"/optimize/{job_id}/finish-now")

        assert finish_response.status_code == 200
        assert finish_response.json()["finishNowRequested"] is True
        completed = wait_for_job_status(job_id, "feasible")
        assert completed["score"] == 7
        assert completed["xlsxReady"] is True
        assert any(
            f"[server:job] finish-now-requested job_id={job_id} status=running client_uuid=" in message
            for message in caplog.messages
        )

    def test_optimize_job_finish_now_interrupts_ortools_search_between_solution_callbacks(self, monkeypatch):
        class BlockingCpSolver:
            def __init__(self):
                self.solve_started = threading.Event()
                self.stop_search_called = threading.Event()

            def Solve(self, model, callback=None):
                self.solve_started.set()
                if not self.stop_search_called.wait(timeout=2):
                    raise AssertionError("finish-now did not interrupt OR-Tools search")
                return cp_model.FEASIBLE

            def StopSearch(self):
                self.stop_search_called.set()

        blocking_solver = BlockingCpSolver()

        def fake_schedule(*args, **kwargs):
            solver = ORToolsSolver()
            solver.set_objective(0, maximize=True)
            solver.solver = blocking_solver
            solver.solve(should_stop=kwargs["should_stop"])
            return "fake_df", {}, 7, "FEASIBLE", None

        def fake_export_to_excel(df, output_buffer, cell_export_info):
            output_buffer.write(b"fake xlsx bytes")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)
        monkeypatch.setattr(serve.exporter, "export_to_excel", fake_export_to_excel)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "running")
        assert blocking_solver.solve_started.wait(timeout=1)

        finish_response = client.post(f"/optimize/{job_id}/finish-now")

        assert finish_response.status_code == 200
        completed = wait_for_job_status(job_id, "feasible")
        assert blocking_solver.stop_search_called.is_set()
        assert completed["score"] == 7
        assert completed["xlsxReady"] is True

    def test_optimize_job_control_rejects_solver_without_stop_support(self):
        job = serve.optimize_job_store.create_job(
            input_name="pulp.yaml",
            client_uuid="test-client",
            solver="pulp/cbc",
            prettify=True,
            timeout=60,
        )
        serve.optimize_job_store.update_job(job.id, status=serve.OptimizeJobStatus.RUNNING)

        cancel_response = client.post(f"/optimize/{job.id}/cancel")
        finish_response = client.post(f"/optimize/{job.id}/finish-now")

        assert cancel_response.status_code == 409
        assert cancel_response.json()["detail"]["solver"] == "pulp/cbc"
        assert "does not support" in cancel_response.json()["detail"]["message"]
        assert finish_response.status_code == 409
        assert finish_response.json()["detail"]["solver"] == "pulp/cbc"

    def test_optimize_job_allows_multiple_sse_connections(self, fake_successful_scheduler):
        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        with client.stream("GET", f"/optimize/{job_id}/events") as first_stream:
            first_body = first_stream.read().decode("utf-8")
        with client.stream("GET", f"/optimize/{job_id}/events") as second_stream:
            second_body = second_stream.read().decode("utf-8")

        assert "event: complete" in first_body
        assert "event: complete" in second_body
        assert '"jobId": "' + job_id + '"' in first_body
        assert '"jobId": "' + job_id + '"' in second_body

    def test_optimize_job_failed_fallback_streams_error_event(self):
        job = serve.optimize_job_store.create_job(
            input_name="failed.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        serve.optimize_job_store.update_job(
            job.id,
            status=serve.OptimizeJobStatus.FAILED,
            error="solver failed",
            finished_at=datetime.now(UTC),
        )
        job.events.clear()

        body = "".join(serve._stream_optimize_job_events(job))

        assert "event: error" in body
        assert "event: complete" not in body
        assert '"status": "failed"' in body

    def test_optimize_job_terminal_update_and_event_are_atomic(self, monkeypatch):
        job = serve.optimize_job_store.create_job(
            input_name="atomic.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        serve.optimize_job_store.update_job(job.id, status=serve.OptimizeJobStatus.RUNNING)
        job.events.clear()
        finish_locked = threading.Event()
        original_finish_locked = serve.optimize_jobs_state._finish_optimize_job_locked

        def finish_after_signalling_lock(finished_job, event, updates):
            finish_locked.set()
            original_finish_locked(finished_job, event, updates)

        monkeypatch.setattr(serve.optimize_jobs_state, "_finish_optimize_job_locked", finish_after_signalling_lock)

        with job.condition:
            finish_thread = threading.Thread(
                target=serve.optimize_job_store.finish_job,
                args=(job.id, "complete"),
                kwargs={
                    "status": serve.OptimizeJobStatus.OPTIMAL,
                    "score": 42,
                    "finished_at": datetime.now(UTC),
                },
            )
            finish_thread.start()

            assert finish_locked.wait(timeout=1)
            assert finish_thread.is_alive()
            assert job.status == serve.OptimizeJobStatus.RUNNING
            assert job.events == []

        finish_thread.join(timeout=1)

        assert not finish_thread.is_alive()
        assert job.status == serve.OptimizeJobStatus.OPTIMAL
        assert job.events[0]["event"] == "complete"
        assert job.events[0]["data"]["score"] == 42
        assert "".join(serve._stream_optimize_job_events(job)).count("event: complete") == 1

    def test_optimize_job_delete_removes_completed_job(self, fake_successful_scheduler, caplog):
        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        delete_response = client.delete(f"/optimize/{job_id}")

        assert delete_response.status_code == 200
        assert delete_response.json() == {"deleted": True, "jobId": job_id}
        assert client.get(f"/optimize/{job_id}").status_code == 404
        assert any(
            f"[server:job] deleted job_id={job_id} status=optimal client_uuid=" in message
            for message in caplog.messages
        )

    def test_optimize_job_expiration_removes_finished_jobs(self, caplog):
        job = serve.optimize_job_store.create_job(
            input_name="expired.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout=1,
        )
        serve.optimize_job_store.update_job(
            job.id,
            status=serve.OptimizeJobStatus.OPTIMAL,
            finished_at=datetime.now(UTC) - timedelta(seconds=serve.OPTIMIZE_JOB_TTL_SECONDS + 1),
        )

        response = client.get(f"/optimize/{job.id}")

        assert response.status_code == 404
        assert any(
            f"[server:job] expired job_id={job.id} status=optimal reason=ttl client_uuid=" in message
            for message in caplog.messages
        )

    def test_optimize_job_retries_generated_id_collision(self, monkeypatch):
        generated_ids = iter(
            [
                types.SimpleNamespace(hex="collision"),
                types.SimpleNamespace(hex="fresh"),
            ]
        )
        monkeypatch.setattr(serve.optimize_jobs_state.uuid, "uuid4", lambda: next(generated_ids))
        existing_job = serve.OptimizeJob(
            id="opt_collision",
            status=serve.OptimizeJobStatus.OPTIMAL,
            created_at=datetime.now(UTC),
            input_name="existing.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=False,
            timeout=None,
            finished_at=datetime.now(UTC),
        )
        with serve.optimize_jobs_state._optimize_jobs_lock:
            serve.optimize_jobs_state._optimize_jobs[existing_job.id] = existing_job

        job = serve.optimize_job_store.create_job(
            input_name="new.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )

        assert job.id == "opt_fresh"
        assert "opt_collision" in serve.optimize_jobs_state._optimize_jobs
        assert serve.optimize_jobs_state._optimize_jobs["opt_fresh"] is job

    def test_optimize_executor_runs_one_job_at_a_time(self):
        assert serve.OPTIMIZE_MAX_WORKERS == 1

    def test_optimize_jobs_report_and_publish_updated_queue_positions(self):
        first = serve.optimize_job_store.create_job(
            input_name="first.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        second = serve.optimize_job_store.create_job(
            input_name="second.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )

        assert serve.optimize_job_store.job_response(first)["queuePosition"] == 1
        assert serve.optimize_job_store.job_response(second)["queuePosition"] == 2

        serve.optimize_job_store.update_job(first.id, status=serve.OptimizeJobStatus.RUNNING)
        serve.optimize_job_store.refresh_queue_positions()

        assert serve.optimize_job_store.job_response(first)["queuePosition"] is None
        assert serve.optimize_job_store.job_response(second)["queuePosition"] == 1
        assert second.events[-1] == {
            "event": "status",
            "data": {"status": "queued", "queuePosition": 1},
        }

    def test_optimize_job_cancels_queued_job_immediately_for_any_solver(self, caplog):
        first = serve.optimize_job_store.create_job(
            input_name="first.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        second = serve.optimize_job_store.create_job(
            input_name="second.yaml",
            client_uuid="test-client",
            solver="pulp/cbc",
            prettify=True,
            timeout=60,
        )

        response = client.post(f"/optimize/{first.id}/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert response.json()["queuePosition"] is None
        assert serve.optimize_job_store.job_response(second)["queuePosition"] == 1
        assert any(
            f"[server:job] cancel-requested job_id={first.id} status=cancelled client_uuid=" in message
            for message in caplog.messages
        )
        assert any(
            f"[server:job] completed job_id={first.id} status=cancelled " in message for message in caplog.messages
        )

    def test_optimize_job_heartbeat_updates_client_liveness(self):
        job = serve.optimize_job_store.create_job(
            input_name="heartbeat.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        initial_heartbeat = job.last_client_heartbeat_at

        response = client.post(f"/optimize/{job.id}/heartbeat")

        assert response.status_code == 200
        assert response.json() == {"jobId": job.id, "status": "queued"}
        assert job.last_client_heartbeat_at is not None
        assert initial_heartbeat is not None
        assert job.last_client_heartbeat_at >= initial_heartbeat

    def test_optimize_job_heartbeat_rejects_terminal_job(self):
        job = serve.optimize_job_store.create_job(
            input_name="finished.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        serve.optimize_job_store.update_job(
            job.id, status=serve.OptimizeJobStatus.CANCELLED, finished_at=datetime.now(UTC)
        )

        response = client.post(f"/optimize/{job.id}/heartbeat")

        assert response.status_code == 409
        assert response.json()["detail"]["status"] == "cancelled"

    def test_optimize_job_update_rejects_unknown_fields(self):
        job = serve.optimize_job_store.create_job(
            input_name="invalid-update.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )

        with pytest.raises(ValueError, match="Unknown optimization job fields: statuz"):
            serve.optimize_job_store.update_job(job.id, statuz=serve.OptimizeJobStatus.RUNNING)

        assert not hasattr(job, "statuz")

    def test_job_is_cancelled_after_client_heartbeat_timeout(self, caplog):
        job = serve.optimize_job_store.create_job(
            input_name="expired-heartbeat.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        last_heartbeat_at = job.last_client_heartbeat_at
        assert last_heartbeat_at is not None

        expired = serve.optimize_job_store.cancel_jobs_with_expired_heartbeats(
            last_heartbeat_at + timedelta(seconds=serve.OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS)
        )

        assert expired == [job.id]
        response = serve.optimize_job_store.job_response(job)
        assert response["status"] == "cancelled"
        assert response["clientHeartbeatExpired"] is True
        assert response["error"] == "Optimization cancelled because the client heartbeat expired."
        assert any(
            f"[server:job] heartbeat-expired job_id={job.id} status=cancelled action=cancel-requested client_uuid="
            in message
            for message in caplog.messages
        )

    def test_recent_client_heartbeat_prevents_job_cancellation(self):
        job = serve.optimize_job_store.create_job(
            input_name="alive.yaml",
            client_uuid="test-client",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )
        heartbeat_at = job.created_at + timedelta(seconds=30)
        serve.optimize_job_store.record_client_heartbeat(job.id, heartbeat_at)

        expired = serve.optimize_job_store.cancel_jobs_with_expired_heartbeats(
            job.created_at + timedelta(seconds=serve.OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS)
        )

        assert expired == []
        assert job.status == serve.OptimizeJobStatus.QUEUED
        assert job.client_heartbeat_expired is False

    def test_expired_heartbeat_requests_running_job_stop_even_for_non_interruptible_solver(self):
        job = serve.optimize_job_store.create_job(
            input_name="running.yaml",
            client_uuid="test-client",
            solver="pulp/cbc",
            prettify=True,
            timeout=60,
        )
        serve.optimize_job_store.update_job(job.id, status=serve.OptimizeJobStatus.RUNNING)
        serve.optimize_job_store.refresh_queue_positions()
        last_heartbeat_at = job.last_client_heartbeat_at
        assert last_heartbeat_at is not None

        serve.optimize_job_store.cancel_jobs_with_expired_heartbeats(
            last_heartbeat_at + timedelta(seconds=serve.OPTIMIZE_CLIENT_HEARTBEAT_TIMEOUT_SECONDS)
        )

        assert job.status == serve.OptimizeJobStatus.CANCELLING
        assert job.cancel_requested is True
        assert job.client_heartbeat_expired is True

    def test_optimize_job_rejects_when_pending_queue_is_full(self, caplog):
        pending_jobs = [
            serve.optimize_job_store.create_job(
                input_name=f"pending-{index}.yaml",
                client_uuid="test-client",
                solver="ortools/cp-sat",
                prettify=True,
                timeout=60,
            )
            for index in range(serve.OPTIMIZE_MAX_PENDING_JOBS)
        ]

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

        assert response.status_code == 429
        assert "queued or running" in response.json()["detail"]
        assert all(serve.optimize_job_store.get_job(job.id) is job for job in pending_jobs)
        assert (
            f"[server:queue] rejected reason=pending_limit pending_jobs={serve.OPTIMIZE_MAX_PENDING_JOBS} "
            f"limit={serve.OPTIMIZE_MAX_PENDING_JOBS}" in caplog.messages
        )

    def test_optimize_job_prunes_oldest_retained_terminal_job(self, fake_successful_scheduler):
        now = datetime.now(UTC)
        with serve.optimize_jobs_state._optimize_jobs_lock:
            for index in range(serve.OPTIMIZE_MAX_RETAINED_JOBS):
                job = serve.OptimizeJob(
                    id=f"opt_retained_{index}",
                    status=serve.OptimizeJobStatus.OPTIMAL,
                    created_at=now - timedelta(seconds=serve.OPTIMIZE_MAX_RETAINED_JOBS - index),
                    input_name=f"retained-{index}.yaml",
                    client_uuid="test-client",
                    solver="ortools/cp-sat",
                    prettify=True,
                    timeout=60,
                    finished_at=now - timedelta(seconds=serve.OPTIMIZE_MAX_RETAINED_JOBS - index),
                )
                serve.optimize_jobs_state._optimize_jobs[job.id] = job

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

        assert response.status_code == 202
        assert "opt_retained_0" not in serve.optimize_jobs_state._optimize_jobs
        assert len(serve.optimize_jobs_state._optimize_jobs) == serve.OPTIMIZE_MAX_RETAINED_JOBS

    def test_optimize_job_rejects_missing_input(self):
        response = client.post("/optimize")

        assert response.status_code == 400
        assert "must be provided" in response.json()["detail"].lower()

    def test_optimize_job_rejects_both_file_and_yaml_content(self):
        with open(VALID_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize",
                files={"file": ("01_1nurse_1shift_1day.yaml", f, "application/x-yaml")},
                data={"yaml_content": "apiVersion: alpha\n"},
            )

        assert response.status_code == 400
        assert "not both" in response.json()["detail"].lower()

    def test_optimize_job_rejects_invalid_file_type(self):
        with open(ERROR_YAML_FILE, "rb") as f:
            response = client.post(
                "/optimize",
                files={"file": ("01_1nurse_1shift_1day_extra_parameter_error.txt", f, "text/plain")},
            )

        assert response.status_code == 400
        assert "invalid file type" in response.json()["detail"].lower()

    def test_optimize_job_rejects_oversized_yaml_content(self):
        response = client.post("/optimize", data={"yaml_content": "a" * (serve.MAX_OPTIMIZATION_YAML_BYTES + 1)})

        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_optimize_job_rejects_oversized_multipart_yaml_content(self):
        response = client.post(
            "/optimize",
            files={"yaml_content": (None, "a" * (serve.MAX_OPTIMIZATION_YAML_BYTES + 1))},
        )

        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_optimize_job_rejects_oversized_file_upload(self):
        response = client.post(
            "/optimize",
            files={
                "file": (
                    "large.yaml",
                    b"a" * (serve.MAX_OPTIMIZATION_YAML_BYTES + 1),
                    "application/x-yaml",
                )
            },
        )

        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_optimize_job_rejects_timeout_over_one_hour(self):
        response = client.post(
            "/optimize",
            data={
                "yaml_content": "apiVersion: alpha\n",
                "timeout": str(serve.MAX_OPTIMIZATION_TIMEOUT_SECONDS + 1),
            },
        )

        assert response.status_code == 400
        assert str(serve.MAX_OPTIMIZATION_TIMEOUT_SECONDS) in response.json()["detail"]

    @pytest.mark.parametrize("timeout", ["0", "-1"])
    def test_optimize_job_rejects_non_positive_timeout(self, timeout):
        response = client.post(
            "/optimize",
            data={
                "yaml_content": "apiVersion: alpha\n",
                "timeout": timeout,
            },
        )

        assert response.status_code == 400
        assert "between 1 and" in response.json()["detail"]

    def test_optimize_job_invalid_http_request_is_captured(self, monkeypatch):
        captured = []

        def fake_capture_invalid_request(request, status_code, detail):
            captured.append((request.url.path, status_code, detail))

        monkeypatch.setattr(serve, "capture_invalid_request", fake_capture_invalid_request)

        response = client.post("/optimize")

        assert response.status_code == 400
        assert captured == [
            (
                "/optimize",
                400,
                "Either 'file' or 'yaml_content' must be provided",
            )
        ]

    def test_optimize_job_request_validation_error_is_captured(self, monkeypatch):
        captured = []

        def fake_capture_invalid_request(request, status_code, detail):
            captured.append((request.url.path, status_code, detail))

        monkeypatch.setattr(serve, "capture_invalid_request", fake_capture_invalid_request)

        response = client.post(
            "/optimize",
            data={
                "yaml_content": "apiVersion: alpha\n",
                "timeout": "not-an-int",
            },
        )

        assert response.status_code == 422
        assert len(captured) == 1
        assert captured[0][0] == "/optimize"
        assert captured[0][1] == 422
        assert captured[0][2][0]["loc"] == ("body", "timeout")

    def test_optimize_job_records_scheduler_failure(self, monkeypatch, caplog):
        def fake_schedule(*args, **kwargs):
            raise ValueError("bad scheduling data")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)

        client.cookies.clear()
        response = client.post("/optimize", data={"yaml_content": "bad: input\n"})
        job_id = response.json()["jobId"]
        client_uuid = client.cookies[serve.CLIENT_UUID_COOKIE_NAME]

        completed = wait_for_job_status(job_id, "failed")
        assert "bad scheduling data" in completed["error"]
        assert serve.UNEXPECTED_ERROR_VERSION_ADVICE in completed["error"]
        assert "Older YAML may not work after breaking changes" in completed["error"]
        assert completed["xlsxReady"] is False
        assert any(
            f"[server:job] failed job_id={job_id} error=bad scheduling data " in message
            and f"client_uuid={client_uuid}" in message
            for message in caplog.messages
        )

    def test_optimize_job_records_no_solution(self, monkeypatch):
        def fake_schedule(*args, **kwargs):
            return None, None, None, "INFEASIBLE", None

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)

        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]

        completed = wait_for_job_status(job_id, "infeasible")
        assert completed["solverStatus"] == "INFEASIBLE"
        assert completed["xlsxReady"] is False

        download = client.get(f"/optimize/{job_id}/xlsx")
        assert download.status_code == 404
        assert download.json()["detail"]["status"] == "infeasible"


class TestServeInternals:
    """Test serve module internal helper behavior."""

    def test_get_app_version_allows_repository_with_different_owner(self, monkeypatch):
        seen = {}

        def fake_check_output(cmd, stderr, text):
            seen["cmd"] = cmd
            seen["stderr"] = stderr
            seen["text"] = text
            return "v1.2.3-dirty\n"

        monkeypatch.setattr("nurse_scheduling.serve.subprocess.check_output", fake_check_output)

        from nurse_scheduling.serve import _get_app_version

        repo_root = Path(serve.__file__).resolve().parents[2]

        assert _get_app_version() == "v1.2.3-dirty"
        assert seen["cmd"][:5] == [
            "git",
            "-c",
            f"safe.directory={repo_root}",
            "-C",
            str(repo_root),
        ]
        assert seen["cmd"][5:] == ["describe", "--tags", "--always", "--dirty"]
        assert seen["text"] is True

    def test_should_enable_sentry_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("DISABLE_SENTRY", "1")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr("nurse_scheduling.sentry.sys", types.SimpleNamespace(modules={}))

        assert app is not None
        from nurse_scheduling.sentry import _should_enable_sentry

        assert _should_enable_sentry() is False

    def test_should_enable_sentry_disabled_during_pytest(self, monkeypatch):
        monkeypatch.delenv("DISABLE_SENTRY", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_serve.py::fake")

        from nurse_scheduling.sentry import _should_enable_sentry

        assert _should_enable_sentry() is False

    def test_should_enable_sentry_true_when_not_disabled(self, monkeypatch):
        monkeypatch.delenv("DISABLE_SENTRY", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr("nurse_scheduling.sentry.sys", types.SimpleNamespace(modules={}))

        from nurse_scheduling.sentry import _should_enable_sentry

        assert _should_enable_sentry() is True


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--log-cli-level=INFO"])
