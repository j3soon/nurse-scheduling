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

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from .jobs.models import Job, JobEvent, ServerActivity, StoredArtifact, StoreLimits


class JobStore(Protocol):
    """Atomic persistence operations required by the job controller."""

    @property
    def store_id(self) -> str:
        """Return the opaque identity shared by clients of this logical store."""
        ...

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

    def claim_next_job(
        self,
        worker_id: str,
        started_at: datetime,
        runtime_identity: Mapping[str, str] | None = None,
    ) -> Job | None:
        """Atomically claim the next queued job for a worker.

        Include runtime identity in the running event when supplied.
        Return the claimed running job, or `None` when the queue is empty.
        """
        ...

    def register_worker(self, worker_id: str, registered_at: datetime, lease_expires_at: datetime) -> bool:
        """Register an idle worker unless its unresolved prior lease prevents it."""
        ...

    def renew_worker(self, worker_id: str, renewed_at: datetime, lease_expires_at: datetime) -> bool:
        """Renew an unexpired worker lease without resurrecting an expired lease."""
        ...

    def unregister_worker(self, worker_id: str) -> None:
        """Remove a worker lease and its active-job association."""
        ...

    def worker_owns_job(self, worker_id: str, job_id: str, observed_at: datetime) -> bool:
        """Return whether a live worker lease is associated with the job."""
        ...

    def get_activity(self, observed_at: datetime) -> ServerActivity:
        """Return aggregate current job states and live workers."""
        ...

    def update_job(
        self,
        job: Job,
        expected_revision: int,
        events: Sequence[JobEvent],
        artifact: StoredArtifact | None = None,
    ) -> Job:
        """Update a job only if no concurrent update has occurred.

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
    ) -> Iterator[JobEvent | None]:
        """Yield new job events, using `None` as a keepalive signal.

        Iteration blocks up to the keepalive interval when no newer event exists.

        Raises:
            JobNotFoundError: If the job does not exist or is deleted while streaming.
        """
        ...

    def find_finished_before(self, cutoff: datetime) -> list[Job]:
        """Return jobs finished before the retention cutoff.

        Maintenance deletes them to keep total number of job history bounded.
        """
        ...

    def find_jobs_without_live_workers(self, observed_at: datetime) -> list[Job]:
        """Return active jobs without a matching live worker lease.

        Maintenance terminates them because their worker is presumed lost.
        """
        ...

    def remove_expired_worker_leases(self, observed_at: datetime) -> list[str]:
        """Remove expired worker leases and return their worker IDs."""
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
