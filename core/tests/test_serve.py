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
import time
import types
from datetime import UTC, datetime, timedelta

# Add the project root to the Python path so imports will work when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

import nurse_scheduling.serve as serve
from nurse_scheduling.solver_interface import SolverProgress
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
        with serve._optimize_jobs_lock:
            serve._optimize_jobs.clear()
        yield
        with serve._optimize_jobs_lock:
            serve._optimize_jobs.clear()

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

    def test_optimize_job_lifecycle_and_xlsx_download(self, fake_successful_scheduler):
        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

        assert response.status_code == 202
        created = response.json()
        job_id = created["jobId"]
        assert job_id.startswith("opt_")
        assert created["status"] in {"queued", "running", "optimal"}
        assert created["links"]["events"] == f"/optimize/{job_id}/events"

        completed = wait_for_job_status(job_id, "optimal")
        assert completed["score"] == 42
        assert completed["solverStatus"] == "OPTIMAL"
        assert completed["xlsxReady"] is True

        download = client.get(f"/optimize/{job_id}/xlsx")
        assert download.status_code == 200
        assert download.content == b"fake xlsx bytes"
        assert download.headers["X-Schedule-Score"] == "42"
        assert download.headers["X-Schedule-Status"] == "OPTIMAL"

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
        assert cancel_response.json()["status"] == "cancelling"
        completed = wait_for_job_status(job_id, "cancelled")
        assert solve_started
        assert completed["error"] == "Optimization cancelled."
        assert completed["xlsxReady"] is False

    def test_optimize_job_finish_now_requests_best_available_result(self, monkeypatch):
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

    def test_optimize_job_control_rejects_solver_without_stop_support(self):
        job = serve._create_optimize_job(
            input_name="pulp.yaml",
            solver="pulp/cbc",
            prettify=True,
            timeout=60,
        )
        serve._update_optimize_job(job.id, status=serve.OptimizeJobStatus.RUNNING)

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

    def test_optimize_job_delete_removes_completed_job(self, fake_successful_scheduler):
        response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})
        job_id = response.json()["jobId"]
        wait_for_job_status(job_id, "optimal")

        delete_response = client.delete(f"/optimize/{job_id}")

        assert delete_response.status_code == 200
        assert delete_response.json() == {"deleted": True, "jobId": job_id}
        assert client.get(f"/optimize/{job_id}").status_code == 404

    def test_optimize_job_expiration_removes_finished_jobs(self):
        job = serve._create_optimize_job(
            input_name="expired.yaml",
            solver="ortools/cp-sat",
            prettify=False,
            timeout=1,
        )
        serve._update_optimize_job(
            job.id,
            status=serve.OptimizeJobStatus.OPTIMAL,
            finished_at=datetime.now(UTC) - timedelta(seconds=serve.OPTIMIZE_JOB_TTL_SECONDS + 1),
        )

        response = client.get(f"/optimize/{job.id}")

        assert response.status_code == 404

    def test_optimize_job_retries_generated_id_collision(self, monkeypatch):
        generated_ids = iter(
            [
                types.SimpleNamespace(hex="collision"),
                types.SimpleNamespace(hex="fresh"),
            ]
        )
        monkeypatch.setattr(serve.uuid, "uuid4", lambda: next(generated_ids))
        existing_job = serve.OptimizeJob(
            id="opt_collision",
            status=serve.OptimizeJobStatus.QUEUED,
            created_at=datetime.now(UTC),
            input_name="existing.yaml",
            solver="ortools/cp-sat",
            prettify=False,
            timeout=None,
        )
        with serve._optimize_jobs_lock:
            serve._optimize_jobs[existing_job.id] = existing_job

        job = serve._create_optimize_job(
            input_name="new.yaml",
            solver="ortools/cp-sat",
            prettify=True,
            timeout=60,
        )

        assert job.id == "opt_fresh"
        assert "opt_collision" in serve._optimize_jobs
        assert serve._optimize_jobs["opt_fresh"] is job

    def test_optimize_executor_runs_one_job_at_a_time(self):
        assert serve.OPTIMIZE_MAX_WORKERS == 1

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

    def test_optimize_job_records_scheduler_failure(self, monkeypatch):
        def fake_schedule(*args, **kwargs):
            raise ValueError("bad scheduling data")

        monkeypatch.setattr(serve.scheduler, "schedule", fake_schedule)

        response = client.post("/optimize", data={"yaml_content": "bad: input\n"})
        job_id = response.json()["jobId"]

        completed = wait_for_job_status(job_id, "failed")
        assert "bad scheduling data" in completed["error"]
        assert serve.UNEXPECTED_ERROR_VERSION_ADVICE in completed["error"]
        assert "Older YAML may not work after breaking changes" in completed["error"]
        assert completed["xlsxReady"] is False

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
        monkeypatch.setattr("nurse_scheduling.serve.sys", types.SimpleNamespace(modules={}))

        assert app is not None
        from nurse_scheduling.serve import _should_enable_sentry

        assert _should_enable_sentry() is False

    def test_should_enable_sentry_disabled_during_pytest(self, monkeypatch):
        monkeypatch.delenv("DISABLE_SENTRY", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_serve.py::fake")

        from nurse_scheduling.serve import _should_enable_sentry

        assert _should_enable_sentry() is False

    def test_should_enable_sentry_true_when_not_disabled(self, monkeypatch):
        monkeypatch.delenv("DISABLE_SENTRY", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr("nurse_scheduling.serve.sys", types.SimpleNamespace(modules={}))

        from nurse_scheduling.serve import _should_enable_sentry

        assert _should_enable_sentry() is True


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--log-cli-level=INFO"])
