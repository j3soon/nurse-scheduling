"""In-memory optimization job state for the FastAPI backend."""

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

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
import json
from queue import Empty, Full, Queue
from threading import Lock
from uuid import uuid4

from .progress import ProgressEvent


JOB_TTL = timedelta(minutes=30)
TERMINAL_STATUSES = {"completed", "failed"}


@dataclass
class OptimizationJob:
    """Single-process optimization job state."""

    id: str
    status: str = "running"
    events: Queue[ProgressEvent] = field(default_factory=lambda: Queue(maxsize=1000))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    filename: str | None = None
    xlsx_bytes: bytes | None = None
    score: int | float | None = None
    solver_status: str | None = None
    error: str | None = None
    lock: Lock = field(default_factory=Lock, repr=False)

    def emit(self, event: ProgressEvent) -> None:
        """Queue a progress event, preserving terminal events when possible."""
        try:
            self.events.put_nowait(event)
        except Full:
            if event.type not in ("completed", "failed"):
                return
            try:
                self.events.get_nowait()
            except Empty:
                pass
            self.events.put_nowait(event)

    def complete(
        self,
        *,
        filename: str,
        xlsx_bytes: bytes,
        score: int | float,
        solver_status: str,
    ) -> None:
        with self.lock:
            self.status = "completed"
            self.filename = filename
            self.xlsx_bytes = xlsx_bytes
            self.score = score
            self.solver_status = solver_status
            self.updated_at = datetime.now(UTC)
        self.emit(
            ProgressEvent(
                type="completed",
                code="completed",
                message="Optimization completed",
                progress=1.0,
                score=score,
            )
        )

    def fail(self, message: str) -> None:
        with self.lock:
            self.status = "failed"
            self.error = message
            self.updated_at = datetime.now(UTC)
        self.emit(ProgressEvent(type="failed", code="failed", message=message))


class OptimizationJobManager:
    """In-memory job manager intended for single-process FastAPI deployments."""

    def __init__(self) -> None:
        self._jobs: dict[str, OptimizationJob] = {}
        self._lock = Lock()

    def create(self) -> OptimizationJob:
        self.cleanup()
        job = OptimizationJob(id=str(uuid4()))
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> OptimizationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cleanup(self) -> None:
        cutoff = datetime.now(UTC) - JOB_TTL
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in TERMINAL_STATUSES and job.updated_at < cutoff
            ]
            for job_id in expired:
                del self._jobs[job_id]


def format_sse(event: ProgressEvent) -> str:
    """Format a progress event as a server-sent event frame."""
    payload = {key: value for key, value in asdict(event).items() if value is not None}
    return f"event: {event.type}\ndata: {json.dumps(payload)}\n\n"
