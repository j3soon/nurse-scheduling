"""Background worker that claims and executes optimization jobs."""

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

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from ...sentry import capture_optimize_exception
from ..config import DEFAULT_TIMEOUT_GRACE_SECONDS
from ..errors import JobNotFoundError
from ..solver_capabilities import solver_supports_finish_now
from .controller import JobController
from .models import Job, JobFailure, JobState, WorkerLease
from .process_executor import (
    ProcessControl,
    ProcessStatus,
    run_optimization_process,
)
from .runner import OptimizationRunner


server_logger = logging.getLogger("nurse_scheduling.server")
CONTROL_POLL_SECONDS = 1.0
"""Maximum delay before forwarding a cooperative solver control."""


class JobWorker:
    """Own one process-local claim/run loop."""

    def __init__(
        self,
        controller: JobController,
        runner: OptimizationRunner,
        *,
        worker_id: str,
        claim_poll_seconds: float,
        worker_lease_seconds: float,
        timeout_grace_seconds: float = DEFAULT_TIMEOUT_GRACE_SECONDS,
        unexpected_error_formatter: Callable[[Exception], str] = str,
    ):
        """Configure a process-local worker without starting its thread."""
        self._controller = controller
        """Controller used for claims, events, control requests, and outcomes."""
        self._runner = runner
        """Runner that performs one blocking optimization execution."""
        self._timeout_grace_seconds = timeout_grace_seconds
        """Additional time before the server forcibly terminates a timed-out job."""
        self._worker_id = worker_id
        """Stable identity recorded on jobs claimed by this worker."""
        self._claim_poll_seconds = claim_poll_seconds
        """Delay between claim attempts and after recoverable loop errors."""
        self._worker_lease_seconds = worker_lease_seconds
        """Maximum time this worker remains live without a successful heartbeat."""
        self._worker_heartbeat_seconds = worker_lease_seconds / 3
        """Worker-renewal interval set to one third of the lease for retry margin."""
        self._unexpected_error_formatter = unexpected_error_formatter
        """Formatter used to produce unexpected failure messages."""
        self._stop = threading.Event()
        """Signal that stops claiming jobs and terminates the active child."""
        self._ready = threading.Event()
        """Whether this worker currently holds a live registered lease."""
        self._executing = threading.Event()
        """Whether the claim loop is still winding down an owned job."""
        self._lock = threading.Lock()
        """Lock guarding worker-thread creation, inspection, and cleanup."""
        self._lease: WorkerLease | None = None
        """Current lease used to claim new work."""
        self._thread: threading.Thread | None = None
        """Daemon claim-loop thread, or `None` when no thread is retained."""
        self._heartbeat_thread: threading.Thread | None = None
        """Always-running worker-presence heartbeat thread."""

    def start(self) -> None:
        """Register this worker and start its claim and heartbeat loops."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            lease = self._controller.register_worker(self._worker_id)
            if lease is None:
                raise RuntimeError(f"Unable to register optimization worker: {self._worker_id}")
            self._lease = lease
            self._stop.clear()
            self._ready.set()
            self._thread = threading.Thread(target=self._run, name="optimization-job-worker", daemon=True)
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat,
                args=(lease,),
                name="optimization-worker-heartbeat",
                daemon=True,
            )
            self._thread.start()
            self._heartbeat_thread.start()
        server_logger.info("[server:worker] started worker_id=%s", self._worker_id)

    def stop(self) -> None:
        """Request shutdown and wait briefly for the worker thread to exit."""
        self._stop.set()
        with self._lock:
            thread = self._thread
            heartbeat_thread = self._heartbeat_thread
        if thread is not None:
            thread.join(timeout=5)
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=5)
        with self._lock:
            lease = self._lease
        try:
            if lease is not None:
                self._controller.unregister_worker(lease)
        except Exception:
            server_logger.exception("[server:worker] failed to unregister worker_id=%s", self._worker_id)
        self._ready.clear()
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None
            if self._heartbeat_thread is heartbeat_thread and (
                heartbeat_thread is None or not heartbeat_thread.is_alive()
            ):
                self._heartbeat_thread = None
            if self._lease == lease:
                self._lease = None

    def is_alive(self) -> bool:
        """Return whether the worker thread is currently running."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def is_ready(self) -> bool:
        """Return whether both worker loops are alive with a registered lease."""
        with self._lock:
            return bool(
                self._ready.is_set()
                and self._thread is not None
                and self._thread.is_alive()
                and self._heartbeat_thread is not None
                and self._heartbeat_thread.is_alive()
            )

    def _heartbeat(self, lease: WorkerLease) -> None:
        """Renew worker presence and recover safely after an expired lease."""
        while not self._stop.is_set():
            seconds_until_expiry = (lease.expires_at - datetime.now(timezone.utc)).total_seconds()
            wait_seconds = min(self._worker_heartbeat_seconds, max(0.0, seconds_until_expiry))
            if self._stop.wait(wait_seconds):
                return
            if not self._claim_loop_is_alive():
                self._unregister_stopped_worker()
                return

            renewed_lease = self._renew_worker_lease(lease)
            if renewed_lease is not None:
                with self._lock:
                    if self._lease == lease:
                        self._lease = renewed_lease
                lease = renewed_lease
                continue

            recovered_lease = self._recover_worker_lease(lease)
            if recovered_lease is None:
                return
            with self._lock:
                self._lease = recovered_lease
            self._ready.set()
            lease = recovered_lease

    def _claim_loop_is_alive(self) -> bool:
        """Return whether the job claim loop is still running."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _unregister_stopped_worker(self) -> None:
        """Clear readiness and unregister after the claim loop exits."""
        self._ready.clear()
        with self._lock:
            lease = self._lease
        try:
            if lease is not None:
                self._controller.unregister_worker(lease)
        except Exception:
            server_logger.exception(
                "[server:worker] failed to unregister stopped worker_id=%s",
                self._worker_id,
            )
        with self._lock:
            if self._lease == lease:
                self._lease = None

    def _renew_worker_lease(self, lease: WorkerLease) -> WorkerLease | None:
        """Renew once, retaining the current lease through a brief store outage."""
        try:
            return self._controller.renew_worker(lease)
        except Exception:
            server_logger.exception("[server:worker] failed to renew worker_id=%s", self._worker_id)
            if datetime.now(timezone.utc) < lease.expires_at:
                return lease
            return None

    def _recover_worker_lease(self, lease: WorkerLease) -> WorkerLease | None:
        """Reconcile an uncertain renewal before replacing a lost lease."""
        try:
            renewed_lease = self._controller.renew_worker(lease)
        except Exception:
            server_logger.exception(
                "[server:worker] failed to reconcile worker lease worker_id=%s",
                self._worker_id,
            )
        else:
            if renewed_lease is not None:
                server_logger.info("[server:worker] worker lease reconciled worker_id=%s", self._worker_id)
                return renewed_lease

        self._ready.clear()
        server_logger.error("[server:worker] worker lease expired worker_id=%s", self._worker_id)
        while not self._stop.is_set():
            if not self._claim_loop_is_alive():
                self._unregister_stopped_worker()
                return None
            try:
                self._controller.expire_worker_claims()
                if not self._executing.is_set():
                    recovered_lease = self._controller.register_worker(self._worker_id)
                    if recovered_lease is not None:
                        server_logger.info("[server:worker] worker lease recovered worker_id=%s", self._worker_id)
                        return recovered_lease
            except Exception:
                server_logger.exception("[server:worker] failed to recover worker_id=%s", self._worker_id)
            self._stop.wait(self._claim_poll_seconds)
        return None

    def _run(self) -> None:
        """Claim and execute jobs until shutdown is requested.

        Recoverable claim and reporting failures are logged before retrying.
        """
        while not self._stop.is_set():
            if not self._ready.is_set():
                self._stop.wait(self._claim_poll_seconds)
                continue
            with self._lock:
                lease = self._lease
            if lease is None:
                self._stop.wait(self._claim_poll_seconds)
                continue
            try:
                job = self._controller.claim_next_job(lease)
            except Exception:
                server_logger.exception("[server:worker] failed to claim job worker_id=%s", self._worker_id)
                self._stop.wait(self._claim_poll_seconds)
                continue
            if job is None:
                self._stop.wait(self._claim_poll_seconds)
                continue
            self._executing.set()
            try:
                self._execute(job, lease)
            except Exception:
                server_logger.exception(
                    "[server:worker] failed to report execution outcome job_id=%s worker_id=%s",
                    job.id,
                    self._worker_id,
                )
                self._stop.wait(self._claim_poll_seconds)
            finally:
                self._executing.clear()

    def _execute(self, job: Job, lease: WorkerLease) -> None:
        """Execute one claimed job and report its progress and outcome."""
        content = b""
        # Stops the control thread and aborts the child after ownership loss.
        monitor_stop = threading.Event()
        # Asks the solver to stop while preserving its current result.
        finish_now_requested = threading.Event()
        # Cancels the job and discards its result, forcing termination if needed.
        cancellation_requested = threading.Event()

        control_thread: threading.Thread | None = None
        try:
            content = self._controller.get_input(job.id)

            def publish(event_type: str, data: dict, score: int | None) -> None:
                """Persist one runner event and its score when available."""
                if score is None:
                    self._controller.record_event(job.id, event_type, data, lease=lease)
                else:
                    self._controller.record_score_and_event(job.id, score, data, lease=lease)

            def watch_controls() -> None:
                """Poll cancellation, finish-now, and ownership controls."""
                stop_check_error_logged = False
                while not monitor_stop.is_set():
                    try:
                        if self._controller.is_stop_requested(job.id, lease):
                            current = self._controller.get_job(job.id)
                            if current.state.terminal or current.worker_id != lease.worker_id:
                                monitor_stop.set()
                                return
                            if current.cancel_requested:
                                cancellation_requested.set()
                                return
                            elif current.early_completion_requested:
                                finish_now_requested.set()
                            else:
                                monitor_stop.set()
                                return
                        stop_check_error_logged = False
                    except JobNotFoundError:
                        monitor_stop.set()
                        return
                    except Exception:
                        # The worker heartbeat logs store outages and keeps retrying.
                        if not stop_check_error_logged:
                            server_logger.exception(
                                "[server:worker] failed to check stop request job_id=%s",
                                job.id,
                            )
                            stop_check_error_logged = True
                    monitor_stop.wait(CONTROL_POLL_SECONDS)

            control_thread = threading.Thread(
                target=watch_controls,
                name=f"optimization-job-control-{job.id}",
                daemon=True,
            )
            control_thread.start()
            finish_now_supported = solver_supports_finish_now(job.request.solver)

            def process_control() -> ProcessControl | None:
                """Return the highest-priority control for the optimization child."""
                if monitor_stop.is_set():
                    return ProcessControl.ABORT
                if not self._ready.is_set():
                    return ProcessControl.ABORT
                if cancellation_requested.is_set():
                    return ProcessControl.CANCEL
                if self._stop.is_set():
                    return ProcessControl.ABORT
                if finish_now_supported and finish_now_requested.is_set():
                    return ProcessControl.FINISH
                return None

            process_result = run_optimization_process(
                self._runner,
                job,
                content,
                event_callback=publish,
                control=process_control,
                hard_timeout_seconds=job.request.timeout_seconds + self._timeout_grace_seconds,
                finish_now_enabled=finish_now_supported,
            )
            if process_result.status is ProcessStatus.COMPLETED:
                if process_result.output is None:
                    raise RuntimeError("Completed optimization process has no output")
                self._controller.complete_job(
                    job.id,
                    process_result.output.result,
                    process_result.output.artifact,
                    lease=lease,
                )
            elif process_result.status is ProcessStatus.FAILED:
                if process_result.failure is None:
                    raise RuntimeError("Failed optimization process has no failure")
                self._controller.fail_job(job.id, process_result.failure, lease=lease)
            elif process_result.status is ProcessStatus.CANCELLED:
                self._controller.complete_cancellation(job.id, lease)
            elif process_result.status is ProcessStatus.ABORTED:
                server_logger.info(
                    "[server:worker] stopped child execution job_id=%s worker_id=%s",
                    job.id,
                    self._worker_id,
                )
            else:
                raise RuntimeError(f"Unknown optimization process status: {process_result.status}")
        except JobNotFoundError:
            server_logger.warning("[server:worker] job disappeared while running job_id=%s", job.id)
        except Exception as error:
            failure = JobFailure(code="optimization_failed", message=self._unexpected_error_formatter(error))
            try:
                failed = self._controller.fail_job(job.id, failure, lease=lease)
            except Exception:
                try:
                    capture_optimize_exception(job, content, error)
                except Exception:
                    server_logger.exception("[server:worker] failed to capture optimization error job_id=%s", job.id)
                raise
            if failed.state == JobState.CANCELLED:
                server_logger.info(
                    "[server:worker] cancelled-after-exception job_id=%s exception_type=%s error=%s worker_id=%s",
                    job.id,
                    type(error).__name__,
                    str(error),
                    self._worker_id,
                    exc_info=(type(error), error, error.__traceback__),
                )
                return
            try:
                capture_optimize_exception(job, content, error)
            except Exception:
                server_logger.exception("[server:worker] failed to capture optimization error job_id=%s", job.id)
            server_logger.exception(
                "[server:worker] failed job_id=%s worker_id=%s",
                job.id,
                self._worker_id,
                exc_info=(type(error), error, error.__traceback__),
            )
        finally:
            monitor_stop.set()
            if control_thread is not None:
                control_thread.join(timeout=1)
