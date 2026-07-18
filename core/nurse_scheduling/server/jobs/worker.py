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

from ...sentry import capture_optimize_exception
from ..config import (
    DEFAULT_CANCEL_GRACE_SECONDS,
    DEFAULT_TIMEOUT_GRACE_SECONDS,
)
from ..errors import JobNotFoundError, OptimizationExecutionError
from .controller import JobController
from ..solver_capabilities import solver_supports_finish_now, solver_supports_graceful_cancel
from .models import Job, JobFailure, JobState
from .process_executor import (
    OptimizationForcedCancellation,
    OptimizationProcessAborted,
    ProcessOptimizationExecutor,
)
from .runner import OptimizationRunner


server_logger = logging.getLogger("nurse_scheduling.server")
CONTROL_POLL_SECONDS = 0.05
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
        claim_lease_seconds: float,
        timeout_grace_seconds: float = DEFAULT_TIMEOUT_GRACE_SECONDS,
        cancel_grace_seconds: float = DEFAULT_CANCEL_GRACE_SECONDS,
        unexpected_error_formatter: Callable[[Exception], str] = str,
    ):
        """Configure a process-local worker without starting its thread."""
        self._controller = controller
        """Controller used for claims, events, control requests, and outcomes."""
        self._runner = runner
        """Runner that performs one blocking optimization execution."""
        self._process_executor = ProcessOptimizationExecutor(
            timeout_grace_seconds=timeout_grace_seconds,
            cancel_grace_seconds=cancel_grace_seconds,
        )
        """Child-process supervisor used for every optimization execution."""
        self._worker_id = worker_id
        """Stable identity recorded on jobs claimed by this worker."""
        self._claim_poll_seconds = claim_poll_seconds
        """Delay between claim attempts and after recoverable loop errors."""
        self._claim_heartbeat_seconds = claim_lease_seconds / 3
        """Claim-renewal interval set to one third of the lease for retry margin."""
        self._unexpected_error_formatter = unexpected_error_formatter
        """Formatter used to produce unexpected failure messages."""
        self._stop = threading.Event()
        """Signal that stops claiming jobs and cooperative solver execution."""
        self._lock = threading.Lock()
        """Lock guarding worker-thread creation, inspection, and cleanup."""
        self._thread: threading.Thread | None = None
        """Daemon claim-loop thread, or `None` when no thread is retained."""

    def start(self) -> None:
        """Start the daemon claim loop unless it is already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="optimization-job-worker", daemon=True)
            self._thread.start()
        server_logger.info("[server:worker] started worker_id=%s", self._worker_id)

    def stop(self) -> None:
        """Request shutdown and wait briefly for the worker thread to exit."""
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None

    def is_alive(self) -> bool:
        """Return whether the worker thread is currently running."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """Claim and execute jobs until shutdown is requested.

        Recoverable claim and reporting failures are logged before retrying.
        """
        while not self._stop.is_set():
            try:
                job = self._controller.claim_next_job(self._worker_id)
            except Exception:
                server_logger.exception("[server:worker] failed to claim job worker_id=%s", self._worker_id)
                self._stop.wait(self._claim_poll_seconds)
                continue
            if job is None:
                self._stop.wait(self._claim_poll_seconds)
                continue
            try:
                self._execute(job)
            except Exception:
                server_logger.exception(
                    "[server:worker] failed to report execution outcome job_id=%s worker_id=%s",
                    job.id,
                    self._worker_id,
                )
                self._stop.wait(self._claim_poll_seconds)

    def _execute(self, job: Job) -> None:
        """Execute one claimed job and report its progress and outcome."""
        content = b""
        # Stops the heartbeat and control threads, and aborts the child after claim loss.
        # Its waits set how often the worker renews the claim and checks controls.
        monitor_stop = threading.Event()
        # Asks the solver to stop while preserving its current result.
        finish_now_requested = threading.Event()
        # Cancels the job and discards its result, forcing termination if needed.
        cancellation_requested = threading.Event()

        def renew_claim() -> None:
            """Renew the worker claim until execution ends or the job disappears."""
            while not monitor_stop.wait(self._claim_heartbeat_seconds):
                try:
                    renewed = self._controller.renew_claim(job.id, self._worker_id)
                    if renewed is None or renewed.state.terminal or renewed.worker_id != self._worker_id:
                        monitor_stop.set()
                        return
                except JobNotFoundError:
                    monitor_stop.set()
                    return
                except Exception:
                    server_logger.exception("[server:worker] failed to renew claim job_id=%s", job.id)

        # Lease renewal runs separately because optimization blocks this worker thread.
        heartbeat_thread = threading.Thread(
            target=renew_claim,
            name=f"optimization-job-heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        control_thread: threading.Thread | None = None
        try:
            content = self._controller.get_input(job.id)

            def publish(event_type: str, data: dict, score: int | None) -> None:
                """Persist one runner event and its score when available."""
                if score is None:
                    self._controller.record_event(job.id, event_type, data, worker_id=self._worker_id)
                else:
                    self._controller.record_score_and_event(job.id, score, data, worker_id=self._worker_id)

            def watch_controls() -> None:
                """Poll cancellation, finish-now, and ownership controls."""
                stop_check_error_logged = False
                while not monitor_stop.is_set():
                    try:
                        if self._controller.is_stop_requested(job.id, self._worker_id):
                            current = self._controller.get_job(job.id)
                            if current.state.terminal or current.worker_id != self._worker_id:
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
                        # Claim renewal logs store outages and keeps retrying.
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
            should_stop = finish_now_requested.is_set if solver_supports_finish_now(job.request.solver) else None

            output = self._process_executor.run(
                self._runner,
                job,
                content,
                event_callback=publish,
                should_stop=should_stop,
                should_cancel=cancellation_requested.is_set,
                graceful_cancel=solver_supports_graceful_cancel(job.request.solver),
                should_abort=lambda: self._stop.is_set() or monitor_stop.is_set(),
            )
            self._controller.complete_job(job.id, output.result, output.artifact)
        except OptimizationProcessAborted:
            server_logger.info(
                "[server:worker] stopped child execution job_id=%s worker_id=%s",
                job.id,
                self._worker_id,
            )
        except OptimizationForcedCancellation as error:
            self._controller.force_cancel_job(job.id, str(error))
        except OptimizationExecutionError as error:
            self._controller.fail_job(
                job.id,
                JobFailure(code=error.code, message=str(error)),
            )
        except JobNotFoundError:
            server_logger.warning("[server:worker] job disappeared while running job_id=%s", job.id)
        except Exception as error:
            failure = JobFailure(code="optimization_failed", message=self._unexpected_error_formatter(error))
            try:
                failed = self._controller.fail_job(job.id, failure)
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
            heartbeat_thread.join(timeout=1)
