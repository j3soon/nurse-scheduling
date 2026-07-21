"""Lifecycle-owned periodic maintenance for retained server jobs."""

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

from .jobs.controller import JobController


server_logger = logging.getLogger("nurse_scheduling.server")


class JobMaintenance:
    """Periodically expire lost-worker jobs, leases, and retained history."""

    def __init__(self, controller: JobController, *, interval_seconds: float):
        """Configure periodic job cleanup without starting its thread."""
        self._controller = controller
        """Controller that expires lost-worker jobs, leases, and retained history."""
        self._interval_seconds = interval_seconds
        """Delay between maintenance passes."""
        self._stop = threading.Event()
        """Signal that interrupts the maintenance wait and stops the loop."""
        self._thread: threading.Thread | None = None
        """Daemon maintenance thread, or `None` when no thread is retained."""

    def start(self) -> None:
        """Start the daemon maintenance loop unless it is already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="job-maintenance", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request shutdown and wait briefly for the maintenance thread to exit."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        if self._thread is thread and (thread is None or not thread.is_alive()):
            self._thread = None

    def _run(self) -> None:
        """Apply worker lease and retention cleanup at each interval.

        Failures are logged without terminating future maintenance passes.
        """
        while not self._stop.wait(self._interval_seconds):
            try:
                self._controller.expire_worker_claims()
                self._controller.expire_jobs()
            except Exception:
                server_logger.exception("[server:maintenance] job retention check failed")
