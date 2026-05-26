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

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
import json
from threading import Condition, Lock
from uuid import uuid4

from .progress import ProgressEvent


JOB_TTL = timedelta(minutes=30)
MAX_EVENTS_PER_JOB = 1000
MAX_JOBS = 32
MAX_RUNNING_JOBS = 2
TERMINAL_STATUSES = {"completed", "failed"}


class JobLimitError(RuntimeError):
    """Raised when the in-memory job manager cannot accept another job."""


@dataclass
class OptimizationJob:
    """Single-process optimization job state."""

    id: str
    status: str = "running"
    events: deque[tuple[int, ProgressEvent]] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS_PER_JOB))
    next_event_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    filename: str | None = None
    xlsx_bytes: bytes | None = None
    score: int | float | None = None
    solver_status: str | None = None
    error: str | None = None
    condition: Condition = field(default_factory=Condition, repr=False)

    def snapshot(self) -> dict[str, object]:
        """Return public job status metadata."""
        with self.condition:
            return {
                "job_id": self.id,
                "status": self.status,
                "score": self.score,
                "solver_status": self.solver_status,
                "error": self.error,
                "filename": self.filename,
            }

    def emit(self, event: ProgressEvent) -> None:
        """Append a progress event and notify stream subscribers."""
        with self.condition:
            self.events.append((self.next_event_index, event))
            self.next_event_index += 1
            self.updated_at = datetime.now(UTC)
            self.condition.notify_all()

    def events_after(self, offset: int) -> tuple[int, list[ProgressEvent]]:
        """Return available events at or after a monotonic stream offset."""
        with self.condition:
            next_event_index = self.next_event_index
            events = [event for index, event in self.events if index >= offset]
        if offset < 0:
            offset = 0
        return next_event_index, events

    def complete(
        self,
        *,
        filename: str,
        xlsx_bytes: bytes,
        score: int | float,
        solver_status: str,
    ) -> None:
        event = ProgressEvent(
            type="completed",
            code="completed",
            message="Optimization completed",
            progress=1.0,
            score=score,
        )
        with self.condition:
            self.status = "completed"
            self.filename = filename
            self.xlsx_bytes = xlsx_bytes
            self.score = score
            self.solver_status = solver_status
            self.updated_at = datetime.now(UTC)
            self.events.append((self.next_event_index, event))
            self.next_event_index += 1
            self.condition.notify_all()

    def fail(self, message: str) -> None:
        event = ProgressEvent(type="failed", code="failed", message=message)
        with self.condition:
            self.status = "failed"
            self.error = message
            self.updated_at = datetime.now(UTC)
            self.events.append((self.next_event_index, event))
            self.next_event_index += 1
            self.condition.notify_all()


class OptimizationJobManager:
    """In-memory job manager intended for single-process FastAPI deployments."""

    def __init__(self) -> None:
        self._jobs: dict[str, OptimizationJob] = {}
        self._lock = Lock()

    def create(self) -> OptimizationJob:
        self.cleanup()
        with self._lock:
            running_jobs = sum(1 for job in self._jobs.values() if job.status == "running")
            if running_jobs >= MAX_RUNNING_JOBS:
                raise JobLimitError("Too many optimization jobs are already running")
            if len(self._jobs) >= MAX_JOBS:
                raise JobLimitError("Too many optimization jobs are retained")
            job = OptimizationJob(id=str(uuid4()))
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
