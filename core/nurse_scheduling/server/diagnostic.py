"""Run bounded production diagnostics through the public optimization API."""

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

# This file is mostly AI generated.

# This production diagnostic exercises the configured public API endpoint:
#
# - Discovers runtime identities from three sources:
#   1. /info responses sampled concurrently over 100 fresh connections by
#      default, with bounded request concurrency.
#   2. Queued job.state_changed SSE events, whose runtime identifies the HTTP
#      process that accepted each job.
#   3. Running job.state_changed SSE events, whose runtime and worker_id identify
#      the process and worker that claimed each job.
#   Merges all three sources to detect mixed service, API, app version,
#   deployment, process instance, job backend, or job store identities. Validates
#   /info fields and cache policy. Reports distinct responses instead of every
#   sample. These checks can reveal stale deployments, mixed storage, separate
#   stores, or excess workers.
# - Submits the real large-ward scheduling case with a one-hour solver timeout
#   and verifies job visibility across independently routed requests. Continues
#   to the configured limit until the newest five jobs remain queued for 10
#   seconds by default.
# - Compares observed running jobs with expected concurrency. After feasible
#   solver results appear, cancels the first running job and finishes the rest
#   early. Processes the originally queued jobs in batches matching the peak
#   observed concurrency, waits for each batch to run, then finishes every job.
# - Makes bounded cancellation and deletion attempts for every submitted job,
#   even after failures. Prints an immediate connection confirmation, a minimal
#   pass, fail, or inconclusive summary, and phase timings. Saves identity
#   samples, job histories, findings, and request errors in a timestamped JSON
#   report. The exit code does not control or stop the backend.
# - Results are observational. Public routing and unrelated users can hide
#   instances or interfere with capacity and queue timing, so unusual results do
#   not by themselves prove that the code or deployment is incorrect.

import argparse
import json
import math
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from ..sentry import flush_sentry, init_sentry
from ..version import get_app_version
from .auth import AUTH_TOKEN_ENV_NAME

DEFAULT_TARGET_URL = "https://api.nursescheduling.org"
DEFAULT_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "tests/testcases/real/large-ward-with-87-people-2025-11.yaml"
)
TERMINAL_STATES = {"completed", "cancelled", "failed"}
QUEUED_JOB_TARGET = 5
PHASE_NAMES = (
    "readiness",
    "info_sampling",
    "info_analysis",
    "queue_saturation",
    "queue_transition",
    "identity_analysis",
    "cleanup",
)
RUNTIME_IDENTITY_FIELDS = {
    "service_name",
    "api_version",
    "app_version",
    "deployment_id",
    "instance_id",
    "started_at",
    "job_backend",
    "job_store_id",
}


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer diagnostic setting."""
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float_env(name: str, default: float) -> float:
    """Read a positive finite floating-point diagnostic setting."""
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


@dataclass(frozen=True)
class DiagnosticConfig:
    """Validated settings controlling one bounded diagnostic run."""

    target_url: str = DEFAULT_TARGET_URL
    scenario_path: Path = DEFAULT_SCENARIO_PATH
    report_dir: Path = Path("/tmp/nurse-scheduling-diagnostics")
    info_samples: int = 100
    parallel_requests: int = 10
    expected_concurrency: int = 3
    max_jobs: int = 128
    queue_stable_seconds: float = 10.0
    startup_timeout_seconds: float = 120.0
    workflow_timeout_seconds: float = 600.0
    incumbent_timeout_seconds: float = 45.0
    cleanup_timeout_seconds: float = 30.0
    request_timeout_seconds: float = 10.0
    job_timeout_seconds: int = 60 * 60
    poll_seconds: float = 0.5
    submit_interval_seconds: float = 0.25
    auth_token: str | None = None
    """Shared token sent to a target that requires authentication."""

    def __post_init__(self) -> None:
        """Reject unsafe or unusable diagnostic settings."""
        target = self.target_url.rstrip("/")
        parsed = urlsplit(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("DIAGNOSTIC_TARGET_URL must be an absolute HTTP or HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("DIAGNOSTIC_TARGET_URL must not contain credentials")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("DIAGNOSTIC_TARGET_URL must not contain a path, query, or fragment")
        if not self.scenario_path.is_file():
            raise ValueError(f"Diagnostic scenario was not found: {self.scenario_path}")
        for name in (
            "info_samples",
            "parallel_requests",
            "expected_concurrency",
            "max_jobs",
            "job_timeout_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "queue_stable_seconds",
            "startup_timeout_seconds",
            "workflow_timeout_seconds",
            "incumbent_timeout_seconds",
            "cleanup_timeout_seconds",
            "request_timeout_seconds",
            "poll_seconds",
            "submit_interval_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive")
        object.__setattr__(self, "target_url", target)
        auth_token = (self.auth_token or "").strip()
        if auth_token and parsed.scheme != "https":
            raise ValueError("DIAGNOSTIC_AUTH_TOKEN requires DIAGNOSTIC_TARGET_URL to use HTTPS")
        object.__setattr__(self, "auth_token", auth_token or None)

    @classmethod
    def from_env(
        cls,
        *,
        target_url: str | None = None,
        scenario_path: Path | None = None,
        report_dir: Path | None = None,
    ) -> "DiagnosticConfig":
        """Load a diagnostic configuration from environment variables."""
        return cls(
            target_url=target_url or os.getenv("DIAGNOSTIC_TARGET_URL", DEFAULT_TARGET_URL),
            scenario_path=scenario_path or Path(os.getenv("DIAGNOSTIC_SCENARIO_PATH", str(DEFAULT_SCENARIO_PATH))),
            report_dir=report_dir or Path(os.getenv("DIAGNOSTIC_REPORT_DIR", "/tmp/nurse-scheduling-diagnostics")),
            info_samples=_positive_int_env("DIAGNOSTIC_INFO_SAMPLES", 100),
            parallel_requests=_positive_int_env("DIAGNOSTIC_PARALLEL_REQUESTS", 10),
            expected_concurrency=_positive_int_env("DIAGNOSTIC_EXPECTED_CONCURRENCY", 3),
            max_jobs=_positive_int_env("DIAGNOSTIC_MAX_JOBS", 128),
            queue_stable_seconds=_positive_float_env("DIAGNOSTIC_QUEUE_STABLE_SECONDS", 10.0),
            startup_timeout_seconds=_positive_float_env("DIAGNOSTIC_STARTUP_TIMEOUT_SECONDS", 120.0),
            workflow_timeout_seconds=_positive_float_env("DIAGNOSTIC_WORKFLOW_TIMEOUT_SECONDS", 600.0),
            incumbent_timeout_seconds=_positive_float_env("DIAGNOSTIC_INCUMBENT_TIMEOUT_SECONDS", 45.0),
            cleanup_timeout_seconds=_positive_float_env("DIAGNOSTIC_CLEANUP_TIMEOUT_SECONDS", 30.0),
            request_timeout_seconds=_positive_float_env("DIAGNOSTIC_REQUEST_TIMEOUT_SECONDS", 10.0),
            job_timeout_seconds=_positive_int_env("DIAGNOSTIC_JOB_TIMEOUT_SECONDS", 60 * 60),
            poll_seconds=_positive_float_env("DIAGNOSTIC_POLL_SECONDS", 0.5),
            submit_interval_seconds=_positive_float_env("DIAGNOSTIC_SUBMIT_INTERVAL_SECONDS", 0.25),
            auth_token=os.getenv("DIAGNOSTIC_AUTH_TOKEN") or os.getenv(AUTH_TOKEN_ENV_NAME),
        )


@dataclass(frozen=True)
class Finding:
    """One concise operator-facing diagnostic finding."""

    level: str
    code: str
    message: str


@dataclass
class DiagnosticJob:
    """Locally tracked state for one submitted diagnostic job."""

    id: str
    input_name: str
    transitions: list[str] = field(default_factory=list)
    deleted: bool = False

    def observe(self, state: str | None) -> None:
        """Record a state only when it differs from the latest observation."""
        if state is not None and (not self.transitions or self.transitions[-1] != state):
            self.transitions.append(state)


class PublicDiagnostic:
    """Exercise public service identity, shared state, and queue transitions."""

    def __init__(
        self,
        config: DiagnosticConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.run_id = uuid4().hex
        self.started_at = datetime.now(timezone.utc)
        self.started_monotonic = time.monotonic()
        self.workflow_deadline = self.started_monotonic + config.workflow_timeout_seconds
        self.startup_attempts: list[dict[str, Any]] = []
        self.info_samples: list[dict[str, Any]] = []
        self.accepted_http_workers: list[dict[str, Any]] = []
        self.runners: list[dict[str, Any]] = []
        self.accepted_identity_jobs: set[str] = set()
        self.runner_identity_jobs: set[str] = set()
        self.event_jobs_checked: set[str] = set()
        self.seen_identity_events: set[tuple[str, str | None, str]] = set()
        self.jobs: list[DiagnosticJob] = []
        self.findings: list[Finding] = []
        self.request_errors: list[str] = []
        self.inconclusive = False
        self.visibility_split = False
        self.max_running = 0
        self.batch_sizes: list[int] = []
        self.queue_transition = "not_run"
        self.cleanup = "not_run"
        self.cleanup_cancel_attempted_jobs: set[str] = set()
        self.connection_announced = False
        self.phase_durations_seconds = {name: 0.0 for name in PHASE_NAMES}
        self._state_lock = threading.Lock()

    def _new_client(self) -> httpx.Client:
        """Create a client with an independent connection pool."""
        return httpx.Client(
            base_url=self.config.target_url,
            timeout=self.config.request_timeout_seconds,
            follow_redirects=False,
            transport=self.transport,
            headers=self._client_headers(),
        )

    def _client_headers(self) -> dict[str, str]:
        """Build the headers shared by every diagnostic request."""
        headers = {"User-Agent": "nurse-scheduling-public-diagnostic/1"}
        if self.config.auth_token is not None:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        return headers

    def _add_finding(self, level: str, code: str, message: str) -> None:
        """Append one deduplicated finding."""
        finding = Finding(level=level, code=code, message=message)
        with self._state_lock:
            if finding not in self.findings:
                self.findings.append(finding)

    def _fail(self, code: str, message: str) -> None:
        """Record a definite diagnostic failure."""
        self._add_finding("error", code, message)

    def _mark_inconclusive(self, code: str, message: str) -> None:
        """Record an observation that prevents a conclusive pass."""
        self.inconclusive = True
        self._add_finding("warning", code, message)

    def _warn(self, code: str, message: str) -> None:
        """Record a non-failing caveat."""
        self._add_finding("warning", code, message)

    def _record_request_error(self, operation: str, error: object) -> None:
        """Retain bounded request details outside the concise findings."""
        detail = f"{operation}: {error}"
        with self._state_lock:
            if detail not in self.request_errors and len(self.request_errors) < 100:
                self.request_errors.append(detail)

    @contextmanager
    def _measure_phase(self, name: str) -> Iterator[None]:
        """Accumulate elapsed time for one diagnostic phase."""
        started = time.monotonic()
        try:
            yield
        finally:
            self.phase_durations_seconds[name] += time.monotonic() - started

    def _sleep(self, seconds: float) -> None:
        """Sleep without extending past the overall workflow deadline."""
        remaining = self.workflow_deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(seconds, remaining))

    def _workflow_request_timeout(self) -> float | None:
        """Return a positive request timeout within the workflow deadline."""
        remaining = self.workflow_deadline - time.monotonic()
        if remaining <= 0:
            return None
        return max(0.001, min(self.config.request_timeout_seconds, remaining))

    def _run_request_batch(
        self,
        count: int,
        request: Callable[[int, float], Any],
    ) -> dict[int, Any]:
        """Run indexed requests with bounded concurrency and elapsed time."""
        if count <= 0:
            return {}
        workers = min(count, self.config.parallel_requests)
        results: dict[int, Any] = {}
        if workers == 1:
            for index in range(count):
                timeout = self._workflow_request_timeout()
                if timeout is None:
                    break
                results[index] = request(index, timeout)
            return results

        executor = ThreadPoolExecutor(max_workers=workers)
        pending: dict[Future[Any], int] = {}
        next_index = 0
        try:
            while next_index < count and len(pending) < workers:
                timeout = self._workflow_request_timeout()
                if timeout is None:
                    break
                pending[executor.submit(request, next_index, timeout)] = next_index
                next_index += 1

            while pending:
                remaining = self.workflow_deadline - time.monotonic()
                if remaining <= 0:
                    break
                done, _ = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
                if not done:
                    break
                for future in done:
                    index = pending.pop(future)
                    results[index] = future.result()
                while next_index < count and len(pending) < workers:
                    timeout = self._workflow_request_timeout()
                    if timeout is None:
                        break
                    pending[executor.submit(request, next_index, timeout)] = next_index
                    next_index += 1

            for future, index in list(pending.items()):
                if future.done():
                    results[index] = future.result()
                    del pending[future]
        finally:
            for future in pending:
                future.cancel()
            executor.shutdown(wait=not pending, cancel_futures=True)
        return results

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any] | None:
        """Decode a JSON object response without raising."""
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _sample_statistics(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group identical HTTP observations while preserving first-seen order."""
        grouped: dict[str, dict[str, Any]] = {}
        for sample in samples:
            key = json.dumps(sample, sort_keys=True, separators=(",", ":"))
            if key in grouped:
                grouped[key]["count"] += 1
            else:
                grouped[key] = {"count": 1, **sample}
        return list(grouped.values())

    def _observe_event_identity(
        self,
        job_id: str,
        event_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Record accepted-process and runner identities once per persisted event."""
        state = payload.get("state")
        identity = payload.get("runtime")
        if not isinstance(identity, dict) or state not in {"queued", "running"}:
            return
        key = (job_id, event_id, str(state))
        if key in self.seen_identity_events:
            return
        self.seen_identity_events.add(key)
        if state == "queued":
            self.accepted_http_workers.append(identity)
            self.accepted_identity_jobs.add(job_id)
            return
        runner = dict(identity)
        if "worker_id" in payload:
            runner["worker_id"] = payload["worker_id"]
        self.runners.append(runner)
        self.runner_identity_jobs.add(job_id)

    def _sample_info(self, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        """Request one uncached info sample over a fresh connection pool."""
        sample: dict[str, Any] = {"statusCode": None, "body": None, "cacheControl": None}
        try:
            with self._new_client() as client:
                response = client.get(
                    "/info",
                    params={"diagnosticSample": uuid4().hex},
                    headers={"Cache-Control": "no-cache", "Connection": "close"},
                    timeout=timeout_seconds or self.config.request_timeout_seconds,
                )
            sample["statusCode"] = response.status_code
            sample["body"] = self._json_object(response)
            sample["cacheControl"] = response.headers.get("Cache-Control")
        except httpx.HTTPError as error:
            sample["error"] = f"{type(error).__name__}: {error}"
            self._record_request_error("GET /info", error)
        return sample

    def _announce_connection(self, sample: dict[str, Any]) -> None:
        """Print once after receiving the first HTTP response from the target."""
        if self.connection_announced or sample.get("statusCode") is None:
            return
        body = sample.get("body")
        status = body.get("status") if isinstance(body, dict) else "unknown"
        print(
            f"CONNECTED target={self.config.target_url} http_status={sample['statusCode']} status={status}",
            flush=True,
        )
        self.connection_announced = True

    def _sample_info_concurrently(self, count: int) -> list[dict[str, Any]]:
        """Collect independent info samples with bounded concurrency."""
        samples = self._run_request_batch(
            count,
            lambda _index, timeout: self._sample_info(timeout_seconds=timeout),
        )
        return [samples[index] for index in sorted(samples)]

    def _collect_info(self) -> bool:
        """Wait for one ready response, then collect the configured sample count."""
        ready_seen = False
        with self._measure_phase("readiness"):
            startup_deadline = min(
                self.workflow_deadline,
                time.monotonic() + self.config.startup_timeout_seconds,
            )
            while time.monotonic() < startup_deadline:
                sample = self._sample_info()
                self._announce_connection(sample)
                body = sample.get("body")
                ready_seen = (
                    sample.get("statusCode") == 200 and isinstance(body, dict) and body.get("status") == "ready"
                )
                if ready_seen:
                    self.info_samples.append(sample)
                    break
                self.startup_attempts.append(sample)
                self._sleep(min(2.0, self.config.poll_seconds))

        if not ready_seen:
            self._mark_inconclusive(
                "info_not_ready",
                "No ready /info response was observed before the startup deadline.",
            )
            return False

        with self._measure_phase("info_sampling"):
            remaining = self.config.info_samples - len(self.info_samples)
            self.info_samples.extend(self._sample_info_concurrently(remaining))
        return True

    def _analyze_info(self) -> None:
        """Validate readiness, response fields, and cache behavior."""
        samples = [*self.startup_attempts, *self.info_samples]
        required_fields = {"status", *RUNTIME_IDENTITY_FIELDS}
        for sample in samples:
            if sample.get("statusCode") == 404:
                self._fail("info_endpoint_missing", "At least one routed backend does not provide /info.")
            body = sample.get("body")
            if isinstance(body, dict):
                missing = sorted(required_fields.difference(body))
                if missing:
                    self._fail("incomplete_info", f"An /info response omitted fields: {', '.join(missing)}.")
                empty = sorted(field for field in required_fields if field in body and not body[field])
                if empty:
                    self._fail("empty_info_identity", f"An /info response had empty fields: {', '.join(empty)}.")
            if sample.get("statusCode") is not None and "no-store" not in str(sample.get("cacheControl") or "").lower():
                self._warn("info_cache_control", "At least one /info response did not declare Cache-Control: no-store.")
        unusable_count = sum(
            not (
                sample.get("statusCode") == 200
                and isinstance(sample.get("body"), dict)
                and sample["body"].get("status") == "ready"
            )
            for sample in self.info_samples
        )
        if unusable_count:
            self._mark_inconclusive(
                "intermittent_readiness",
                f"Observed {unusable_count} non-ready /info responses during sampling.",
            )
        if len(self.info_samples) < self.config.info_samples:
            self._mark_inconclusive(
                "info_sampling_incomplete",
                f"Collected {len(self.info_samples)} of {self.config.info_samples} requested /info samples.",
            )

    def _runtime_identities(self) -> list[dict[str, Any]]:
        """Return identities observed through info, acceptance, and execution."""
        samples = [*self.startup_attempts, *self.info_samples]
        info_identities = [
            sample["body"]
            for sample in samples
            if isinstance(sample.get("body"), dict) and sample["body"].get("instance_id") is not None
        ]
        return [*info_identities, *self.accepted_http_workers, *self.runners]

    def _analyze_runtime_identities(self) -> None:
        """Detect missing or mixed identities across every observation source."""
        for source, identities, required_fields in (
            ("accepted HTTP worker", self.accepted_http_workers, RUNTIME_IDENTITY_FIELDS),
            ("runner", self.runners, {*RUNTIME_IDENTITY_FIELDS, "worker_id"}),
        ):
            for identity in identities:
                missing = sorted(required_fields.difference(identity))
                if missing:
                    self._fail("incomplete_event_identity", f"A {source} identity omitted: {', '.join(missing)}.")
                empty = sorted(field for field in required_fields if field in identity and not identity[field])
                if empty:
                    self._fail("empty_event_identity", f"A {source} identity had empty fields: {', '.join(empty)}.")

        for job in self.jobs:
            if job.id not in self.event_jobs_checked:
                self._mark_inconclusive(
                    "job_identity_not_checked",
                    "At least one submitted job event stream could not be checked for runtime identity.",
                )
                continue
            if job.id not in self.accepted_identity_jobs:
                self._fail("accepted_identity_missing", "A submitted job did not identify its accepting HTTP worker.")
            if "running" in job.transitions and job.id not in self.runner_identity_jobs:
                self._fail("runner_identity_missing", "A running job did not identify its actual runner.")

        identities = self._runtime_identities()
        service_names = {str(body["service_name"]) for body in identities if body.get("service_name") is not None}
        api_versions = {str(body["api_version"]) for body in identities if body.get("api_version") is not None}
        versions = {str(body["app_version"]) for body in identities if body.get("app_version") is not None}
        deployments = {str(body["deployment_id"]) for body in identities if body.get("deployment_id") is not None}
        instances = {str(body["instance_id"]) for body in identities if body.get("instance_id") is not None}
        backends = {str(body["job_backend"]) for body in identities if body.get("job_backend") is not None}
        stores = {str(body["job_store_id"]) for body in identities if body.get("job_store_id") is not None}

        if service_names and service_names != {"nurse-scheduling-api"}:
            self._fail("unexpected_service_identity", f"Observed service names: {', '.join(sorted(service_names))}.")
        if len(api_versions) > 1:
            self._fail("mixed_api_versions", f"Observed multiple API versions: {', '.join(sorted(api_versions))}.")
        if len(versions) > 1:
            self._fail("mixed_app_versions", f"Observed multiple app versions: {', '.join(sorted(versions))}.")
        if len(deployments) > 1:
            self._fail("mixed_deployments", f"Observed multiple deployment IDs: {', '.join(sorted(deployments))}.")
        if "unmanaged" in deployments:
            self._fail("unmanaged_deployment", "The backend did not receive a launch-specific deployment ID.")
        if len(backends) > 1:
            self._fail("mixed_job_backends", f"Observed mixed job backends: {', '.join(sorted(backends))}.")
        if len(stores) > 1:
            self._fail("mixed_job_stores", f"Observed multiple job store IDs: {', '.join(sorted(stores))}.")
        if "unconfigured" in stores:
            self._fail("unconfigured_job_store", "The backend did not receive an explicit job store ID.")
        if "memory" in backends and self.config.expected_concurrency > 1:
            self._fail(
                "memory_with_multiple_workers",
                "The expected concurrency is greater than one while the job backend is memory.",
            )
        if "memory" in backends and len(instances) > 1:
            self._fail(
                "split_memory_instances",
                f"Observed {len(instances)} process-local memory instances behind one endpoint.",
            )
        if len(instances) > self.config.expected_concurrency:
            self._fail(
                "unexpected_instance_count",
                f"Observed at least {len(instances)} instances, expected {self.config.expected_concurrency}.",
            )

    def _create_job(self, index: int) -> DiagnosticJob | None:
        """Submit one tagged real scenario through the public endpoint."""
        input_name = f"diagnostic-{self.run_id}-{index:03d}.yaml"
        try:
            scenario = self.config.scenario_path.read_bytes()
            with self._new_client() as client:
                response = client.post(
                    "/optimize",
                    files={"file": (input_name, scenario, "application/yaml")},
                    data={
                        "solver": "ortools/cp-sat",
                        "prettify": "false",
                        "timeout": str(self.config.job_timeout_seconds),
                    },
                    headers={"Connection": "close"},
                )
        except (OSError, httpx.HTTPError) as error:
            self._record_request_error("POST /optimize", error)
            self._mark_inconclusive("job_submission_error", "A diagnostic job could not be submitted.")
            return None
        if response.status_code == 429:
            self._mark_inconclusive(
                "job_capacity_reached",
                "The backend rejected a diagnostic job because active capacity was already full.",
            )
            return None
        if response.status_code != 202:
            self._record_request_error("POST /optimize", f"HTTP {response.status_code}: {response.text[:300]}")
            self._mark_inconclusive(
                "job_submission_error", "A diagnostic job submission returned an unexpected response."
            )
            return None
        body = self._json_object(response)
        if body is None or not isinstance(body.get("id"), str):
            self._mark_inconclusive("invalid_job_response", "A diagnostic job response omitted its job ID.")
            return None
        job = DiagnosticJob(id=body["id"], input_name=input_name)
        job.observe(str(body.get("state")) if body.get("state") is not None else None)
        self.jobs.append(job)
        return job

    def _job_for_id(self, job_id: str) -> DiagnosticJob:
        """Return local tracking for a submitted job ID."""
        return next(job for job in self.jobs if job.id == job_id)

    def _get_job(
        self,
        job_id: str,
        *,
        cleanup: bool = False,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        """Fetch one job and detect cross-route state loss."""
        try:
            with self._new_client() as client:
                response = client.get(
                    f"/optimize/{job_id}",
                    headers={"Connection": "close"},
                    timeout=timeout_seconds or self.config.request_timeout_seconds,
                )
        except httpx.HTTPError as error:
            self._record_request_error(f"GET job {job_id}", error)
            return None
        if response.status_code == 404:
            if not cleanup:
                self.visibility_split = True
                self._fail(
                    "job_visibility_split",
                    "A newly created job returned 404 through the same public endpoint.",
                )
            return None
        if response.status_code != 200:
            self._record_request_error(
                f"GET job {job_id}",
                f"HTTP {response.status_code}: {response.text[:300]}",
            )
            return None
        body = self._json_object(response)
        if body is None:
            self._record_request_error(f"GET job {job_id}", "invalid JSON object")
            return None
        self._job_for_id(job_id).observe(str(body.get("state")) if body.get("state") is not None else None)
        return body

    def _get_jobs(self, job_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch independent job snapshots with bounded concurrency."""
        bodies = self._run_request_batch(
            len(job_ids),
            lambda index, timeout: self._get_job(job_ids[index], timeout_seconds=timeout),
        )
        return {job_ids[index]: bodies[index] for index in sorted(bodies) if bodies[index] is not None}

    def _jobs_stay_queued(self, jobs: list[DiagnosticJob]) -> bool:
        """Return whether all supplied jobs remain queued for the stable interval."""
        stable_started: float | None = None
        job_ids = [job.id for job in jobs]
        while time.monotonic() < self.workflow_deadline:
            if stable_started is None:
                snapshots = self._snapshot_jobs()
            else:
                snapshots = self._get_jobs(job_ids)
            if any(job_id not in snapshots for job_id in job_ids):
                if self.visibility_split:
                    return False
                stable_started = None
                self._sleep(self.config.poll_seconds)
                continue
            states = [snapshots[job_id].get("state") for job_id in job_ids]
            if states != ["queued"] * len(jobs):
                return False
            if stable_started is None:
                stable_started = time.monotonic()
            if time.monotonic() - stable_started >= self.config.queue_stable_seconds:
                return True
            self._sleep(self.config.poll_seconds)
        return False

    def _submit_until_queue_is_stable(self) -> list[str]:
        """Submit jobs until the newest target count remains stably queued."""
        for index in range(1, self.config.max_jobs + 1):
            if self.visibility_split:
                break
            job = self._create_job(index)
            if job is None:
                break
            self._get_job(job.id)
            if self.visibility_split:
                break
            self._sleep(self.config.submit_interval_seconds)
            if len(self.jobs) >= QUEUED_JOB_TARGET and self._jobs_stay_queued(self.jobs[-QUEUED_JOB_TARGET:]):
                snapshots = self._snapshot_jobs()
                return [job.id for job in self.jobs if snapshots.get(job.id, {}).get("state") == "queued"]
            if self.visibility_split:
                break
        if not self.visibility_split:
            self._mark_inconclusive(
                "stable_queue_not_observed",
                f"{QUEUED_JOB_TARGET} queued jobs were not observed before submitting at most "
                f"{self.config.max_jobs} jobs.",
            )
        return []

    def _snapshot_jobs(self) -> dict[str, dict[str, Any]]:
        """Fetch one current snapshot of every tracked diagnostic job."""
        snapshots = self._get_jobs([job.id for job in self.jobs])
        running = sum(body.get("state") == "running" for body in snapshots.values())
        self.max_running = max(self.max_running, running)
        return snapshots

    def _replay_job_events(self, job_id: str, *, stop_on_score: bool, read_seconds: float) -> bool:
        """Collect runtime identities and optionally detect a feasible score."""
        event_id: str | None = None
        event_type: str | None = None
        data_lines: list[str] = []
        timeout = httpx.Timeout(
            self.config.request_timeout_seconds, read=min(read_seconds, self.config.request_timeout_seconds)
        )
        try:
            with (
                self._new_client() as client,
                client.stream(
                    "GET",
                    f"/optimize/{job_id}/events",
                    headers={"Accept": "text/event-stream", "Connection": "close"},
                    timeout=timeout,
                ) as response,
            ):
                if response.status_code == 404:
                    self.visibility_split = True
                    self._fail(
                        "job_visibility_split",
                        "A newly created job event stream returned 404 through the public endpoint.",
                    )
                    return False
                if response.status_code != 200:
                    self._record_request_error(f"GET events {job_id}", f"HTTP {response.status_code}")
                    return False
                self.event_jobs_checked.add(job_id)
                for line in response.iter_lines():
                    if line.startswith("id:"):
                        event_id = line.partition(":")[2].strip()
                    elif line.startswith("event:"):
                        event_type = line.partition(":")[2].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line.partition(":")[2].lstrip())
                    elif not line:
                        payload: Any = None
                        if data_lines:
                            try:
                                payload = json.loads("\n".join(data_lines))
                            except json.JSONDecodeError:
                                pass
                        if isinstance(payload, dict):
                            self._observe_event_identity(job_id, event_id, payload)
                            if (
                                stop_on_score
                                and event_type == "job.progressed"
                                and isinstance(payload.get("score"), (int, float))
                            ):
                                return True
                        event_id = None
                        event_type = None
                        data_lines = []
        except httpx.ReadTimeout:
            return False
        except httpx.HTTPError as error:
            self._record_request_error(f"GET events {job_id}", error)
        return False

    def _collect_job_identities(self, job_id: str) -> None:
        """Replay one job's available identity events without waiting for progress."""
        self._replay_job_events(job_id, stop_on_score=False, read_seconds=0.25)

    def _event_stream_has_score(self, job_id: str) -> bool:
        """Return whether replayed events contain a feasible incumbent score."""
        return self._replay_job_events(job_id, stop_on_score=True, read_seconds=0.75)

    def _post_control(self, job_id: str, control: str) -> bool:
        """Request one supported job control operation."""
        try:
            with self._new_client() as client:
                response = client.post(
                    f"/optimize/{job_id}/{control}",
                    headers={"Connection": "close"},
                )
        except httpx.HTTPError as error:
            self._record_request_error(f"POST {control} {job_id}", error)
            return False
        if response.status_code == 404:
            self.visibility_split = True
            self._fail(
                "job_visibility_split",
                "A control request for a newly created job returned 404 through the public endpoint.",
            )
            return False
        if response.status_code != 202:
            self._record_request_error(
                f"POST {control} {job_id}",
                f"HTTP {response.status_code}: {response.text[:300]}",
            )
            return False
        body = self._json_object(response)
        if body is not None:
            self._job_for_id(job_id).observe(str(body.get("state")) if body.get("state") is not None else None)
        return True

    def _wait_for_terminal(self, job_ids: list[str], timeout_seconds: float) -> dict[str, dict[str, Any]]:
        """Wait for the requested jobs to reach any terminal state."""
        deadline = min(self.workflow_deadline, time.monotonic() + timeout_seconds)
        terminal: dict[str, dict[str, Any]] = {}
        while time.monotonic() < deadline:
            pending_ids = [job_id for job_id in job_ids if job_id not in terminal]
            snapshots = self._get_jobs(pending_ids)
            terminal.update(
                {job_id: body for job_id, body in snapshots.items() if body.get("state") in TERMINAL_STATES}
            )
            if len(terminal) == len(job_ids):
                return terminal
            if self.visibility_split:
                return terminal
            self._sleep(self.config.poll_seconds)
        return terminal

    def _wait_for_running(self, job_ids: list[str], timeout_seconds: float) -> bool:
        """Wait for all requested queued jobs to become running."""
        deadline = min(self.workflow_deadline, time.monotonic() + timeout_seconds)
        while time.monotonic() < deadline:
            snapshots = self._get_jobs(job_ids)
            if len(snapshots) != len(job_ids):
                if self.visibility_split:
                    return False
                self._sleep(self.config.poll_seconds)
                continue
            states = [str(snapshots[job_id].get("state")) for job_id in job_ids]
            if states and all(state == "running" for state in states):
                return True
            if any(state in TERMINAL_STATES for state in states):
                return False
            self._sleep(self.config.poll_seconds)
        return False

    def _select_jobs_with_incumbents(self, running_ids: list[str], count: int) -> list[str]:
        """Wait for the requested number of running jobs to report feasible scores."""
        selected: list[str] = []
        deadline = min(self.workflow_deadline, time.monotonic() + self.config.incumbent_timeout_seconds)
        while time.monotonic() < deadline and len(selected) < count:
            for job_id in running_ids:
                if job_id not in selected and self._event_stream_has_score(job_id):
                    selected.append(job_id)
                    if len(selected) == count:
                        break
            if len(selected) < count:
                self._sleep(self.config.poll_seconds)
        return selected

    def _finish_running_jobs(self, job_ids: list[str]) -> bool:
        """Finish a running batch after every job reports a feasible result."""
        if not job_ids:
            return True
        finish_ids = self._select_jobs_with_incumbents(job_ids, len(job_ids))
        if len(finish_ids) < len(job_ids):
            self._mark_inconclusive(
                "incumbents_not_observed",
                f"Only {len(finish_ids)} of {len(job_ids)} running jobs reported feasible scores.",
            )
            return False
        if not all(self._post_control(job_id, "finish-now") for job_id in finish_ids):
            self.queue_transition = "fail"
            return False
        completed = self._wait_for_terminal(finish_ids, self.config.incumbent_timeout_seconds)
        if len(completed) != len(finish_ids):
            self._mark_inconclusive("finish_now_timeout", "Finish-now jobs did not become terminal in time.")
            return False
        if any(completed[job_id].get("state") != "completed" for job_id in finish_ids):
            self._fail("finish_now_failed", "A finish-now job did not complete successfully.")
            self.queue_transition = "fail"
            return False
        return True

    def _exercise_queue_transition(self, queued_ids: list[str]) -> None:
        """Release initial jobs, then finish every queued job in observed-size batches."""
        snapshots = self._snapshot_jobs()
        running_ids = [job_id for job_id, body in snapshots.items() if body.get("state") == "running"]
        if self.max_running > self.config.expected_concurrency:
            self._fail(
                "unexpected_running_concurrency",
                f"Observed {self.max_running} running diagnostic jobs, expected {self.config.expected_concurrency}.",
            )
        elif self.max_running < self.config.expected_concurrency:
            self._mark_inconclusive(
                "insufficient_running_jobs",
                f"Observed at most {self.max_running} running diagnostic jobs, expected "
                f"{self.config.expected_concurrency}.",
            )

        batch_size = self.max_running
        if batch_size == 0:
            self._mark_inconclusive("no_running_jobs", "No running diagnostic jobs were observed.")
            return
        if len(running_ids) != batch_size:
            self._mark_inconclusive(
                "running_batch_changed",
                f"Peak concurrency was {batch_size}, but {len(running_ids)} jobs were running before controls.",
            )
            return

        cancel_id = running_ids[0]
        finish_ids = running_ids[1:]
        ready_running_ids = self._select_jobs_with_incumbents(running_ids, len(running_ids))
        if len(ready_running_ids) < len(running_ids):
            self._mark_inconclusive(
                "incumbents_not_observed",
                f"Only {len(ready_running_ids)} of {len(running_ids)} running jobs reported feasible scores.",
            )
            return
        controls_ok = self._post_control(cancel_id, "cancel")
        controls_ok = all(self._post_control(job_id, "finish-now") for job_id in finish_ids) and controls_ok
        if not controls_ok:
            self.queue_transition = "fail"
            return

        released_ids = [cancel_id, *finish_ids]
        released = self._wait_for_terminal(released_ids, self.config.incumbent_timeout_seconds)
        if len(released) != len(released_ids):
            self._mark_inconclusive("release_timeout", "The controlled jobs did not become terminal in time.")
            return
        if released[cancel_id].get("state") != "cancelled":
            self._fail("running_cancel_failed", "The first running job was not cancelled.")
            self.queue_transition = "fail"
            return
        if any(released[job_id].get("state") != "completed" for job_id in finish_ids):
            self._fail("finish_now_failed", "A finish-now job did not complete successfully.")
            self.queue_transition = "fail"
            return

        for offset in range(0, len(queued_ids), batch_size):
            batch_ids = queued_ids[offset : offset + batch_size]
            self.batch_sizes.append(len(batch_ids))
            if not self._wait_for_running(batch_ids, self.config.incumbent_timeout_seconds):
                self._mark_inconclusive(
                    "queued_jobs_did_not_run",
                    f"A queued batch of {len(batch_ids)} jobs did not transition to running.",
                )
                self.queue_transition = "inconclusive"
                return
            if not self._finish_running_jobs(batch_ids):
                return

        final_snapshots = self._snapshot_jobs()
        if any(body.get("state") not in TERMINAL_STATES for body in final_snapshots.values()):
            self._fail("diagnostic_jobs_still_active", "Diagnostic jobs remained active after batch processing.")
            self.queue_transition = "fail"
            return
        self.queue_transition = "pass"

    def _cleanup_request_timeout(self, deadline: float) -> float:
        """Return a positive request timeout within the cleanup deadline."""
        remaining = deadline - time.monotonic()
        return max(0.001, min(self.config.request_timeout_seconds, remaining))

    def _run_cleanup_attempts(
        self,
        jobs: list[DiagnosticJob],
        deadline: float,
        attempt: Callable[[DiagnosticJob, float], None],
    ) -> None:
        """Run cleanup requests for every supplied job with bounded concurrency."""
        if not jobs:
            return
        workers = min(len(jobs), self.config.parallel_requests)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(attempt, job, deadline) for job in jobs]
            for future in futures:
                future.result()

    def _cleanup_cancel_attempt(self, job: DiagnosticJob, deadline: float) -> None:
        """Make one direct cancellation attempt for an active or unknown job."""
        with self._state_lock:
            self.cleanup_cancel_attempted_jobs.add(job.id)
        try:
            with self._new_client() as client:
                response = client.post(
                    f"/optimize/{job.id}/cancel",
                    timeout=self._cleanup_request_timeout(deadline),
                )
        except httpx.HTTPError as error:
            self._record_request_error(f"cleanup cancel {job.id}", error)
            return
        if response.status_code == 404:
            return
        if response.status_code != 202:
            self._record_request_error(
                f"cleanup cancel {job.id}",
                f"HTTP {response.status_code}",
            )
            return
        body = self._json_object(response)
        if body is not None:
            job.observe(str(body.get("state")) if body.get("state") is not None else None)

    def _request_cleanup_cancellations(self) -> None:
        """Attempt cancellation once for every job not known to be terminal."""
        candidates = [
            job
            for job in self.jobs
            if not job.deleted
            and job.id not in self.cleanup_cancel_attempted_jobs
            and (not job.transitions or job.transitions[-1] not in TERMINAL_STATES)
        ]
        if not candidates:
            return
        deadline = time.monotonic() + self.config.cleanup_timeout_seconds
        self._run_cleanup_attempts(candidates, deadline, self._cleanup_cancel_attempt)

    def _cleanup_one_attempt(self, job: DiagnosticJob, deadline: float) -> None:
        """Try one fresh routed connection to cancel or delete a job."""
        try:
            with self._new_client() as client:
                response = client.get(
                    f"/optimize/{job.id}",
                    timeout=self._cleanup_request_timeout(deadline),
                )
                if response.status_code == 404:
                    return
                body = self._json_object(response) if response.status_code == 200 else None
                if body is None:
                    self._record_request_error(f"cleanup GET {job.id}", f"HTTP {response.status_code}")
                    return
                state = str(body.get("state"))
                job.observe(state)
                if time.monotonic() >= deadline:
                    return
                if state not in TERMINAL_STATES:
                    control = client.post(
                        f"/optimize/{job.id}/cancel",
                        timeout=self._cleanup_request_timeout(deadline),
                    )
                    if control.status_code not in {202, 404}:
                        self._record_request_error(
                            f"cleanup cancel {job.id}",
                            f"HTTP {control.status_code}",
                        )
                    return
                deleted = client.delete(
                    f"/optimize/{job.id}",
                    timeout=self._cleanup_request_timeout(deadline),
                )
                if deleted.status_code == 204:
                    job.deleted = True
                    return
                self._record_request_error(
                    f"cleanup delete {job.id}",
                    f"HTTP {deleted.status_code}",
                )
        except httpx.HTTPError as error:
            self._record_request_error(f"cleanup {job.id}", error)

    def _cleanup_jobs(self) -> None:
        """Bound cancellation and deletion attempts for every submitted job."""
        if not self.jobs:
            self.cleanup = "pass"
            return
        self._request_cleanup_cancellations()
        deadline = time.monotonic() + self.config.cleanup_timeout_seconds
        while time.monotonic() < deadline and not all(job.deleted for job in self.jobs):
            pending_jobs = [job for job in self.jobs if not job.deleted]
            self._run_cleanup_attempts(pending_jobs, deadline, self._cleanup_one_attempt)
            if not all(job.deleted for job in self.jobs):
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(self.config.poll_seconds, remaining))
        if all(job.deleted for job in self.jobs):
            self.cleanup = "pass"
        else:
            self.cleanup = "partial"
            remaining = sum(not job.deleted for job in self.jobs)
            self._mark_inconclusive(
                "cleanup_incomplete",
                f"Cleanup could not confirm deletion of {remaining} diagnostic jobs before its deadline.",
            )

    def run(self) -> dict[str, Any]:
        """Execute all diagnostic phases and return a structured final report."""
        try:
            ready = self._collect_info()
            with self._measure_phase("info_analysis"):
                self._analyze_info()
            if ready and time.monotonic() < self.workflow_deadline:
                with self._measure_phase("queue_saturation"):
                    queued_ids = self._submit_until_queue_is_stable()
                if len(queued_ids) >= QUEUED_JOB_TARGET and not self.visibility_split:
                    with self._measure_phase("queue_transition"):
                        self._exercise_queue_transition(queued_ids)
        except Exception as error:  # noqa: BLE001
            self._record_request_error("unexpected diagnostic error", f"{type(error).__name__}: {error}")
            self._mark_inconclusive("unexpected_error", "The diagnostic stopped after an unexpected internal error.")
        finally:
            try:
                with self._measure_phase("cleanup"):
                    self._request_cleanup_cancellations()
            except Exception as error:  # noqa: BLE001
                self._record_request_error("unexpected cleanup cancellation error", f"{type(error).__name__}: {error}")
                self._mark_inconclusive(
                    "cleanup_cancellation_error",
                    "Initial diagnostic job cancellation stopped after an unexpected internal error.",
                )
            try:
                with self._measure_phase("identity_analysis"):
                    for job in self.jobs:
                        needs_accepted = job.id not in self.accepted_identity_jobs
                        needs_runner = "running" in job.transitions and job.id not in self.runner_identity_jobs
                        if needs_accepted or needs_runner:
                            self._collect_job_identities(job.id)
                    self._analyze_runtime_identities()
            except Exception as error:  # noqa: BLE001
                self._record_request_error("unexpected identity analysis error", f"{type(error).__name__}: {error}")
                self._mark_inconclusive(
                    "identity_analysis_error",
                    "Runtime identity analysis stopped after an unexpected internal error.",
                )
            finally:
                try:
                    with self._measure_phase("cleanup"):
                        self._cleanup_jobs()
                except Exception as error:  # noqa: BLE001
                    self._record_request_error("unexpected cleanup error", f"{type(error).__name__}: {error}")
                    self._mark_inconclusive(
                        "cleanup_error",
                        "Diagnostic job cleanup stopped after an unexpected internal error.",
                    )
        return self.build_report()

    def _identity_counts(self) -> dict[str, int]:
        """Count merged identities from info, accepting processes, and runners."""
        identities = self._runtime_identities()
        return {
            "versions": len(
                {identity.get("app_version") for identity in identities if identity.get("app_version") is not None}
            ),
            "deployments": len(
                {identity.get("deployment_id") for identity in identities if identity.get("deployment_id") is not None}
            ),
            "instances": len(
                {identity.get("instance_id") for identity in identities if identity.get("instance_id") is not None}
            ),
            "runners": len(
                {identity.get("worker_id") for identity in self.runners if identity.get("worker_id") is not None}
            ),
            "stores": len(
                {
                    (identity.get("job_backend"), identity.get("job_store_id"))
                    for identity in identities
                    if identity.get("job_backend") is not None and identity.get("job_store_id") is not None
                }
            ),
        }

    def _job_backend(self) -> str:
        """Summarize the observed job store implementation."""
        backends = sorted(
            {
                str(identity["job_backend"])
                for identity in self._runtime_identities()
                if identity.get("job_backend") is not None
            }
        )
        if not backends:
            return "unknown"
        if len(backends) > 1:
            return "mixed"
        return backends[0]

    def _outcome(self) -> str:
        """Return pass, fail, or inconclusive from accumulated findings."""
        if any(finding.level == "error" for finding in self.findings):
            return "fail"
        if self.inconclusive:
            return "inconclusive"
        return "pass"

    def build_report(self) -> dict[str, Any]:
        """Build a concise summary followed by detailed diagnostic evidence."""
        finished_at = datetime.now(timezone.utc)
        counts = self._identity_counts()
        summary = {
            "outcome": self._outcome(),
            "target": self.config.target_url,
            "job_type": self.config.scenario_path.stem,
            "job_backend": self._job_backend(),
            **counts,
            "maxRunning": self.max_running,
            "queueTransition": self.queue_transition,
            "cleanup": self.cleanup,
            "durationSeconds": round(time.monotonic() - self.started_monotonic, 3),
        }
        return {
            "summary": summary,
            "findings": [asdict(finding) for finding in self.findings],
            "details": {
                "runId": self.run_id,
                "startedAt": self.started_at.isoformat(),
                "finishedAt": finished_at.isoformat(),
                "expectedConcurrency": self.config.expected_concurrency,
                "parallelRequests": self.config.parallel_requests,
                "submittedJobs": len(self.jobs),
                "batchSizes": self.batch_sizes,
                "phaseDurationsSeconds": {name: round(self.phase_durations_seconds[name], 3) for name in PHASE_NAMES},
                "startupSampling": {
                    "attempts": len(self.startup_attempts),
                    "distinctReturns": self._sample_statistics(self.startup_attempts),
                },
                "infoSampling": {
                    "requested": self.config.info_samples,
                    "collected": len(self.info_samples),
                    "distinctReturns": self._sample_statistics(self.info_samples),
                },
                "acceptedHttpWorkers": {
                    "observedJobs": len(self.accepted_identity_jobs),
                    "distinctIdentities": self._sample_statistics(self.accepted_http_workers),
                },
                "runners": {
                    "observedJobs": len(self.runner_identity_jobs),
                    "distinctIdentities": self._sample_statistics(self.runners),
                },
                "jobs": [asdict(job) for job in self.jobs],
                "requestErrors": self.request_errors,
                "caveat": (
                    "Results are observational. Routing and unrelated users can make instance discovery a lower bound "
                    "or make capacity and transition checks inconclusive. A cloned Redis snapshot can duplicate its "
                    "automatically persisted store ID."
                ),
            },
        }


def format_summary(report: dict[str, Any]) -> str:
    """Format the minimal first line of a structured diagnostic report."""
    summary = report["summary"]
    return (
        f"{str(summary['outcome']).upper()} target={summary['target']} job_type={summary['job_type']} "
        f"job_backend={summary['job_backend']} "
        f"versions={summary['versions']} deployments={summary['deployments']} "
        f"instances={summary['instances']} runners={summary['runners']} stores={summary['stores']} "
        f"maxRunning={summary['maxRunning']} queue={str(summary['queueTransition']).upper()} "
        f"cleanup={str(summary['cleanup']).upper()} duration={summary['durationSeconds']}s"
    )


def format_phase_timings(report: dict[str, Any]) -> str:
    """Format one compact line of phase durations."""
    timings = report["details"]["phaseDurationsSeconds"]
    return "TIMING " + " ".join(f"{name}={timings[name]}s" for name in PHASE_NAMES)


def write_report(report: dict[str, Any], report_dir: Path) -> Path:
    """Persist one timestamped JSON report and return its path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    started = str(report["details"]["startedAt"]).replace(":", "").replace("-", "")
    run_id = str(report["details"]["runId"])
    path = report_dir / f"diagnostic-{started}-{run_id[:12]}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def print_report(report: dict[str, Any], report_path: Path | None = None) -> None:
    """Print the compact summary first and optional details afterward."""
    print(format_summary(report))
    print(format_phase_timings(report))
    for finding in report["findings"]:
        print(f"{str(finding['level']).upper()} {finding['code']}: {finding['message']}")
    print("NOTE results are observational. Routing and unrelated users can make checks inconclusive.")
    if report_path is not None:
        print(f"report={report_path}")


def exit_code(report: dict[str, Any]) -> int:
    """Map report outcomes to stable process exit codes."""
    return {"pass": 0, "fail": 1, "inconclusive": 2}[str(report["summary"]["outcome"])]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse optional manual overrides for the environment configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-url", help="Public backend base URL")
    parser.add_argument("--scenario", type=Path, help="YAML scenario to submit")
    parser.add_argument("--report-dir", type=Path, help="Directory for structured JSON reports")
    return parser.parse_args(argv)


def _run(argv: list[str] | None = None) -> int:
    """Run one diagnostic process."""
    args = _parse_args(argv)
    try:
        config = DiagnosticConfig.from_env(
            target_url=args.target_url,
            scenario_path=args.scenario,
            report_dir=args.report_dir,
        )
        config.report_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as error:
        print(f"FAIL configuration: {error}", file=sys.stderr)
        return 1

    report = PublicDiagnostic(config).run()
    try:
        report_path = write_report(report, config.report_dir)
    except OSError as error:
        report_path = None
        print(f"WARNING report_write_failed: {error}", file=sys.stderr)
    print_report(report, report_path)
    return exit_code(report)


def main(argv: list[str] | None = None) -> int:
    """Run diagnostics with process-specific Sentry monitoring."""
    init_sentry(get_app_version(), app="diagnostic")
    try:
        return _run(argv)
    finally:
        flush_sentry()


if __name__ == "__main__":
    raise SystemExit(main())
