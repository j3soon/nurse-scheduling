"""In-process implementation of the optimization job store."""

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

import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import uuid4

from ..errors import (
    JobArtifactNotFoundError,
    JobCapacityError,
    JobInputNotFoundError,
    JobNotFoundError,
    StoreWriteConflictError,
)
from ..jobs.models import Job, JobEvent, JobState, ServerActivity, StoredArtifact, StoreLimits, WorkerLease


@dataclass
class _MemoryJobRecord:
    """All process-local data retained for one job."""

    job: Job
    """Current persisted job snapshot."""
    input_bytes: bytes
    """Original submitted input."""
    artifacts: dict[str, StoredArtifact] = field(default_factory=dict)
    """Generated artifacts indexed by filename."""
    events: list[JobEvent] = field(default_factory=list)
    """Replayable events in insertion order."""
    next_event_id: int = 1
    """Monotonic integer assigned to the next appended event."""


@dataclass
class _MemoryWorkerLease:
    """Process-local worker presence and exclusive job association."""

    token: str
    expires_at: datetime
    active_job_id: str | None = None


class MemoryJobStore:
    """Thread-safe process-local job metadata, queue, events, and blobs."""

    def __init__(self, *, store_id: str | None = None, max_events_per_job: int = 1_000):
        """Initialize an empty store protected by a shared reentrant lock."""
        if max_events_per_job <= 0:
            raise ValueError("max_events_per_job must be positive")
        self._store_id = str(uuid4()) if store_id is None else store_id
        if not self._store_id.strip():
            raise ValueError("store_id must not be empty")
        """Opaque identity unique to this process-local store."""
        self._records: dict[str, _MemoryJobRecord] = {}
        """Job records indexed by job ID."""
        self._workers: dict[str, _MemoryWorkerLease] = {}
        """Worker leases indexed by worker ID."""
        self._max_events_per_job = max_events_per_job
        """Maximum replayable events retained for any one job."""
        self._lock = threading.RLock()
        """Re-entrant lock guarding all record, queue, artifact, and event access."""
        self._changed = threading.Condition(self._lock)
        """Condition backed by `_lock` that adds `wait()` and `notify_all()` for job changes."""

    @property
    def store_id(self) -> str:
        """Return this process-local store's opaque identity."""
        return self._store_id

    def create(
        self,
        job: Job,
        input_bytes: bytes,
        limits: StoreLimits,
        events: Sequence[JobEvent],
    ) -> Job:
        """Atomically create a job while enforcing pending and retained limits.

        The oldest finished jobs are removed when retained capacity is needed.

        Raises:
            StoreWriteConflictError: If the job ID already exists.
            JobCapacityError: If pending or retained capacity is exhausted.
        """
        with self._changed:
            if job.id in self._records:
                raise StoreWriteConflictError(f"Job already exists: {job.id}")
            pending_count = sum(not record.job.state.terminal for record in self._records.values())
            if pending_count >= limits.max_pending:
                raise JobCapacityError("Too many jobs are queued or running")

            while len(self._records) >= limits.max_retained:
                terminal = sorted(
                    (record.job for record in self._records.values() if record.job.state.terminal),
                    key=lambda candidate: candidate.finished_at or candidate.created_at,
                )
                if not terminal:
                    raise JobCapacityError("Too many jobs are retained")
                del self._records[terminal[0].id]

            record = _MemoryJobRecord(job=replace(job, revision=1, queue_position=None), input_bytes=input_bytes)
            self._records[job.id] = record
            created = self._with_queue_position(record.job)
            self._append_events(record, self._with_initial_queue_position(events, created.queue_position))
            self._append_queue_position_events_for_queued_jobs(job.created_at, exclude_job_id=job.id)
            # notify() may wake an unrelated stream; extra notify_all() wake-ups are acceptable because pending jobs are bounded.
            self._changed.notify_all()
            return created

    def get(self, job_id: str) -> Job:
        """Return a job snapshot with its current queue position.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        with self._lock:
            return self._with_queue_position(self._record(job_id).job)

    def get_input(self, job_id: str) -> bytes:
        """Return the original input submitted for a job.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobInputNotFoundError: If the job has no stored input.
        """
        with self._lock:
            record = self._record(job_id)
            if record.input_bytes is None:
                raise JobInputNotFoundError("Job input was not found")
            return record.input_bytes

    def get_artifact(self, job_id: str, name: str) -> StoredArtifact:
        """Return a named artifact stored within a job record.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobArtifactNotFoundError: If the named artifact does not exist.
        """
        with self._lock:
            artifact = self._record(job_id).artifacts.get(name)
            if artifact is None:
                raise JobArtifactNotFoundError("Job artifact was not found")
            return artifact

    def claim_next_job(
        self,
        lease: WorkerLease,
        started_at: datetime,
        runtime_identity: Mapping[str, str] | None = None,
    ) -> Job | None:
        """Atomically assign the oldest queued job to a worker.

        Return the claimed running job, or `None` when the queue is empty.
        """
        with self._changed:
            worker = self._workers.get(lease.worker_id)
            if (
                worker is None
                or worker.token != lease.token
                or worker.expires_at <= started_at
                or worker.active_job_id is not None
            ):
                return None
            queued = sorted(
                (record for record in self._records.values() if record.job.state == JobState.QUEUED),
                key=lambda record: (record.job.created_at, record.job.id),
            )
            if not queued:
                return None
            record = queued[0]
            claimed = replace(
                record.job,
                state=JobState.RUNNING,
                started_at=started_at,
                worker_id=lease.worker_id,
                queue_position=None,
                revision=record.job.revision + 1,
            )
            worker.active_job_id = claimed.id
            record.job = claimed
            self._append_events(
                record,
                [
                    JobEvent(
                        type="job.state_changed",
                        data={
                            "state": JobState.RUNNING.value,
                            "queue_position": None,
                            "cancel_requested": False,
                            "early_completion_requested": False,
                            "worker_id": lease.worker_id,
                            **({"runtime": dict(runtime_identity)} if runtime_identity is not None else {}),
                        },
                        occurred_at=started_at,
                    )
                ],
            )
            self._append_queue_position_events_for_queued_jobs(started_at)
            # notify() may wake an unrelated stream; extra notify_all() wake-ups are acceptable because pending jobs are bounded.
            self._changed.notify_all()
            return claimed

    def register_worker(self, lease: WorkerLease, registered_at: datetime) -> bool:
        """Register an idle worker without replacing a live or unresolved lease."""
        with self._changed:
            existing = self._workers.get(lease.worker_id)
            if existing is not None and (existing.expires_at > registered_at or existing.active_job_id is not None):
                return False
            self._workers[lease.worker_id] = _MemoryWorkerLease(token=lease.token, expires_at=lease.expires_at)
            self._changed.notify_all()
            return True

    def renew_worker(self, lease: WorkerLease, renewed_at: datetime, lease_expires_at: datetime) -> bool:
        """Renew an existing lease only before its current expiry."""
        with self._changed:
            worker = self._workers.get(lease.worker_id)
            if worker is None or worker.token != lease.token or worker.expires_at <= renewed_at:
                return False
            worker.expires_at = lease_expires_at
            self._changed.notify_all()
            return True

    def unregister_worker(self, lease: WorkerLease) -> None:
        """Remove matching worker presence and ownership state."""
        with self._changed:
            worker = self._workers.get(lease.worker_id)
            if worker is not None and worker.token == lease.token:
                del self._workers[lease.worker_id]
            self._changed.notify_all()

    def worker_owns_job(self, worker_id: str, job_id: str, observed_at: datetime) -> bool:
        """Return whether a live worker is associated with the job."""
        with self._lock:
            worker = self._workers.get(worker_id)
            return bool(worker is not None and worker.expires_at > observed_at and worker.active_job_id == job_id)

    def lease_owns_job(self, lease: WorkerLease, job_id: str, observed_at: datetime) -> bool:
        """Return whether this exact live lease is associated with the job."""
        with self._lock:
            worker = self._workers.get(lease.worker_id)
            return bool(
                worker is not None
                and worker.token == lease.token
                and worker.expires_at > observed_at
                and worker.active_job_id == job_id
            )

    def get_activity(self, observed_at: datetime) -> ServerActivity:
        """Return aggregate job states and unexpired worker leases."""
        with self._lock:
            states = [record.job.state for record in self._records.values()]
            return ServerActivity(
                queued_jobs=states.count(JobState.QUEUED),
                running_jobs=states.count(JobState.RUNNING),
                cancelling_jobs=states.count(JobState.CANCELLING),
                online_workers=sum(worker.expires_at > observed_at for worker in self._workers.values()),
            )

    def update_job(
        self,
        job: Job,
        expected_revision: int,
        events: Sequence[JobEvent],
        artifact: StoredArtifact | None = None,
        *,
        worker_lease: WorkerLease | None = None,
        worker_lease_observed_at: datetime | None = None,
    ) -> Job:
        """Update a job if its revision and optional worker lease still match.

        Omit `worker_lease` only for server-authorized API or maintenance
        transitions. Worker-originated updates must include the lease and its
        observation time.

        Raises:
            JobNotFoundError: If the job does not exist.
            StoreWriteConflictError: If the stored revision no longer matches.
        """
        with self._changed:
            record = self._record(job.id)
            if record.job.revision != expected_revision:
                raise StoreWriteConflictError(f"Job revision changed: {job.id}")
            if worker_lease is not None:
                if worker_lease_observed_at is None:
                    raise ValueError("worker_lease_observed_at is required with a worker lease")
                worker = self._workers.get(worker_lease.worker_id)
                if (
                    record.job.worker_id != worker_lease.worker_id
                    or worker is None
                    or worker.token != worker_lease.token
                    or worker.expires_at <= worker_lease_observed_at
                    or worker.active_job_id != job.id
                ):
                    return self._with_queue_position(record.job)
            was_queued = record.job.state == JobState.QUEUED
            updated_job = replace(job, revision=expected_revision + 1, queue_position=None)
            record.job = updated_job
            if updated_job.state.terminal and updated_job.worker_id is not None:
                worker = self._workers.get(updated_job.worker_id)
                if worker is not None and worker.active_job_id == updated_job.id:
                    worker.active_job_id = None
            if artifact is not None:
                record.artifacts[artifact.name] = artifact
            self._append_events(record, events)
            if was_queued and updated_job.state != JobState.QUEUED:
                occurred_at = events[-1].occurred_at if events else datetime.now(updated_job.created_at.tzinfo)
                self._append_queue_position_events_for_queued_jobs(occurred_at)
            # notify() may wake an unrelated stream; extra notify_all() wake-ups are acceptable because pending jobs are bounded.
            self._changed.notify_all()
            return self._with_queue_position(updated_job)

    def stream_events(
        self,
        job_id: str,
        after_id: str | None,
        keepalive_seconds: float,
    ) -> Iterator[JobEvent | None]:
        """Yield events after the requested ID until the job becomes terminal.

        Iteration blocks up to the keepalive interval when no newer event exists.
        Yield `None` when the keepalive interval passes without a new event.

        Raises:
            JobNotFoundError: If the job does not exist or is deleted while streaming.
        """
        try:
            last_seen = int(after_id) if after_id is not None else 0
        except ValueError:
            last_seen = 0

        while True:
            with self._changed:
                record = self._record(job_id)
                available = [event for event in record.events if int(event.id or 0) > last_seen]
                if not available and not record.job.state.terminal:
                    self._changed.wait(timeout=keepalive_seconds)
                    record = self._record(job_id)
                    available = [event for event in record.events if int(event.id or 0) > last_seen]
                    if not available:
                        keepalive = True
                    else:
                        keepalive = False
                else:
                    keepalive = False
                terminal = record.job.state.terminal

            if keepalive:
                yield None
                continue
            for event in available:
                last_seen = int(event.id or last_seen)
                yield event
            if terminal:
                return

    def find_finished_before(self, cutoff: datetime) -> list[Job]:
        """Return jobs finished before the retention cutoff.

        Maintenance deletes them to keep retained job history bounded.
        """
        with self._lock:
            return [
                self._with_queue_position(record.job)
                for record in self._records.values()
                if record.job.finished_at is not None and record.job.finished_at < cutoff
            ]

    def find_jobs_without_live_workers(self, observed_at: datetime) -> list[Job]:
        """Return active jobs without a matching unexpired worker association.

        Maintenance terminates them because their worker is presumed lost.
        """
        with self._lock:
            return [
                self._with_queue_position(record.job)
                for record in self._records.values()
                if record.job.state in {JobState.RUNNING, JobState.CANCELLING}
                and (
                    record.job.worker_id is None
                    or not self.worker_owns_job(record.job.worker_id, record.job.id, observed_at)
                )
            ]

    def remove_expired_worker_leases(self, observed_at: datetime) -> list[str]:
        """Remove worker leases at or before the supplied time."""
        with self._changed:
            expired_ids = [worker_id for worker_id, worker in self._workers.items() if worker.expires_at <= observed_at]
            for worker_id in expired_ids:
                del self._workers[worker_id]
            if expired_ids:
                self._changed.notify_all()
            return expired_ids

    def check_health(self) -> None:
        """The in-process store has no external dependency to probe."""

    def delete(self, job_id: str, expected_revision: int) -> None:
        """Delete a job and its data if its revision still matches.

        Raises:
            JobNotFoundError: If the job does not exist.
            StoreWriteConflictError: If the stored revision no longer matches.
        """
        with self._changed:
            record = self._record(job_id)
            if record.job.revision != expected_revision:
                raise StoreWriteConflictError(f"Job revision changed: {job_id}")
            del self._records[job_id]
            # notify() may wake an unrelated stream; extra notify_all() wake-ups are acceptable because pending jobs are bounded.
            self._changed.notify_all()

    def _record(self, job_id: str) -> _MemoryJobRecord:
        """Return the internal record for a job.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        record = self._records.get(job_id)
        if record is None:
            raise JobNotFoundError("Job was not found")
        return record

    def _with_queue_position(self, job: Job) -> Job:
        """Return a job copy with its queue position derived from current state."""
        if job.state != JobState.QUEUED:
            return replace(job, queue_position=None)
        queued_ids = [
            candidate.id
            for candidate in sorted(
                (record.job for record in self._records.values() if record.job.state == JobState.QUEUED),
                key=lambda candidate: (candidate.created_at, candidate.id),
            )
        ]
        return replace(job, queue_position=queued_ids.index(job.id) + 1)

    def _append_events(self, record: _MemoryJobRecord, events: Sequence[JobEvent]) -> None:
        """Append events with monotonic IDs and discard the oldest overflow."""
        for event in events:
            record.events.append(replace(event, id=str(record.next_event_id)))
            record.next_event_id += 1
        overflow = len(record.events) - self._max_events_per_job
        if overflow > 0:
            del record.events[:overflow]

    @staticmethod
    def _with_initial_queue_position(
        events: Sequence[JobEvent],
        queue_position: int | None,
    ) -> list[JobEvent]:
        """Add the initial queue position to queued state events."""
        return [
            replace(event, data={**event.data, "queue_position": queue_position})
            if event.type == "job.state_changed" and event.data.get("state") == JobState.QUEUED.value
            else event
            for event in events
        ]

    def _append_queue_position_events_for_queued_jobs(
        self,
        occurred_at: datetime,
        exclude_job_id: str | None = None,
    ) -> None:
        """Append current position events for queued jobs except the excluded job."""
        queued = sorted(
            (record for record in self._records.values() if record.job.state == JobState.QUEUED),
            key=lambda record: (record.job.created_at, record.job.id),
        )
        for position, record in enumerate(queued, start=1):
            if record.job.id == exclude_job_id:
                continue
            self._append_events(
                record,
                [
                    JobEvent(
                        type="job.state_changed",
                        data={
                            "state": JobState.QUEUED.value,
                            "queue_position": position,
                            "cancel_requested": False,
                            "early_completion_requested": False,
                        },
                        occurred_at=occurred_at,
                    )
                ],
            )
