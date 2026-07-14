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
from ..errors import JobNotFoundError, OptimizationExecutionError
from .controller import JobController
from .models import JobFailure, solver_supports_stop
from .runner import OptimizationRunner


server_logger = logging.getLogger("nurse_scheduling.server")


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
        unexpected_error_formatter: Callable[[Exception], str] = str,
    ):
        """Configure a process-local worker without starting its thread."""
        self._controller = controller
        """Controller used for claims, events, control requests, and outcomes."""
        self._runner = runner
        """Runner that performs one blocking optimization execution."""
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

    def _execute(self, job) -> None:
        """Execute one claimed job and report its progress and outcome."""
        content = b""
        heartbeat_stop = threading.Event()

        def renew_claim() -> None:
            """Renew the worker claim until execution ends or the job disappears."""
            while not heartbeat_stop.wait(self._claim_heartbeat_seconds):
                try:
                    renewed = self._controller.renew_claim(job.id, self._worker_id)
                    if renewed.state.terminal:
                        return
                except JobNotFoundError:
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
        try:
            content = self._controller.get_input(job.id)

            def publish(event_type: str, data: dict, score: int | None) -> None:
                """Persist one runner event and its score when available."""
                if score is None:
                    self._controller.record_event(job.id, event_type, data)
                else:
                    self._controller.record_score_and_event(job.id, score, data)

            should_stop = None
            if solver_supports_stop(job.request.solver):

                def should_stop() -> bool:
                    """Return whether shutdown or a job control requested a stop."""
                    return self._stop.is_set() or self._controller.is_stop_requested(job.id)

            output = self._runner.run(
                job,
                content,
                event_callback=publish,
                should_stop=should_stop,
            )
            self._controller.complete_job(job.id, output.result, output.artifact)
        except OptimizationExecutionError as error:
            self._controller.fail_job(job.id, JobFailure(code=error.code, message=str(error)))
        except JobNotFoundError:
            server_logger.warning("[server:worker] job disappeared while running job_id=%s", job.id)
        except Exception as error:
            capture_optimize_exception(job, content, error)
            self._controller.fail_job(
                job.id,
                JobFailure(code="optimization_failed", message=self._unexpected_error_formatter(error)),
            )
            server_logger.exception("[server:worker] failed job_id=%s worker_id=%s", job.id, self._worker_id)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
