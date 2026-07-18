"""Storage contract used by the optimization job controller."""

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

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Protocol

from .jobs.models import Job, JobEvent, JobReplayError, JobReplayGap, StoredArtifact, StoreLimits


class JobStore(Protocol):
    """Atomic persistence operations required by the job controller."""

    def create(
        self,
        job: Job,
        input_bytes: bytes,
        limits: StoreLimits,
        events: Sequence[JobEvent],
    ) -> Job:
        """Atomically persist a new job and enforce the store limits.

        Raises:
            StoreWriteConflictError: If the job ID already exists.
            JobCapacityError: If pending or retained capacity is exhausted.
        """
        ...

    def get(self, job_id: str) -> Job:
        """Return the current snapshot of a job.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        ...

    def get_input(self, job_id: str) -> bytes:
        """Return the original input submitted for a job.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobInputNotFoundError: If the job has no stored input.
        """
        ...

    def get_artifact(self, job_id: str, name: str) -> StoredArtifact:
        """Return a named artifact produced by a job.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobArtifactNotFoundError: If the named artifact does not exist.
        """
        ...

    def claim_next(self, worker_id: str, started_at: datetime, claim_expires_at: datetime) -> Job | None:
        """Atomically claim the next queued job for a worker.

        Return the claimed running job, or `None` when the queue is empty.
        """
        ...

    def save(
        self,
        job: Job,
        expected_revision: int,
        events: Sequence[JobEvent],
        artifact: StoredArtifact | None = None,
    ) -> Job:
        """Save a job update only if no concurrent update has occurred.

        Raises:
            JobNotFoundError: If the job does not exist.
            StoreWriteConflictError: If the stored revision no longer matches.
        """
        ...

    def stream_events(
        self,
        job_id: str,
        after_id: str | None,
        keepalive_seconds: float,
    ) -> Iterator[JobEvent | JobReplayError | JobReplayGap | None]:
        """Yield new job events, using `None` as a keepalive signal.

        Iteration blocks up to the keepalive interval when no newer event exists.
        Yield a replay error or replay gap when the requested cursor cannot be
        used for continuous replay.

        Raises:
            JobNotFoundError: If the job does not exist or is deleted while streaming.
        """
        ...

    def find_finished_before(self, cutoff: datetime) -> list[Job]:
        """Return jobs finished before the retention cutoff.

        Maintenance deletes them to keep total number of job history bounded.
        """
        ...

    def find_claimed_before(self, cutoff: datetime) -> list[Job]:
        """Return active jobs whose worker claim expired by the cutoff.

        Maintenance terminates them because their worker is presumed lost.
        """
        ...

    def check_health(self) -> None:
        """Raise an error when the storage backend is unavailable.

        Raises:
            Exception: An implementation-specific backend health error.
        """
        ...

    def delete(self, job_id: str, expected_revision: int) -> None:
        """Delete a job and its data if its revision still matches.

        Raises:
            JobNotFoundError: If the job does not exist.
            StoreWriteConflictError: If the stored revision no longer matches.
        """
        ...
