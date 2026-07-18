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
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from ..errors import (
    JobArtifactNotFoundError,
    JobCapacityError,
    JobInputNotFoundError,
    JobNotFoundError,
    StoreWriteConflictError,
)
from ..jobs.models import (
    Job,
    JobEvent,
    JobEventType,
    JobReplayError,
    JobReplayGap,
    JobState,
    StoredArtifact,
    StoreLimits,
)


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


class MemoryJobStore:
    """Thread-safe process-local job metadata, queue, events, and blobs."""

    def __init__(self, *, max_events_per_job: int = 1_000):
        """Initialize an empty store protected by a shared reentrant lock."""
        if max_events_per_job <= 0:
            raise ValueError("max_events_per_job must be positive")
        self._records: dict[str, _MemoryJobRecord] = {}
        """Job records indexed by job ID."""
        self._max_events_per_job = max_events_per_job
        """Maximum replayable events retained for any one job."""
        self._lock = threading.RLock()
        """Re-entrant lock guarding all record, queue, artifact, and event access."""
        self._changed = threading.Condition(self._lock)
        """Condition backed by `_lock` that adds `wait()` and `notify_all()` for job changes."""

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

    def claim_next(self, worker_id: str, started_at: datetime, claim_expires_at: datetime) -> Job | None:
        """Atomically assign the oldest queued job to a worker.

        Return the claimed running job, or `None` when the queue is empty.
        """
        with self._changed:
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
                worker_id=worker_id,
                claim_expires_at=claim_expires_at,
                queue_position=None,
                revision=record.job.revision + 1,
            )
            record.job = claimed
            self._append_events(
                record,
                [
                    JobEvent(
                        type=JobEventType.STATE_CHANGED,
                        data={
                            "state": JobState.RUNNING.value,
                            "queue_position": None,
                            "cancel_requested": False,
                            "early_completion_requested": False,
                        },
                        occurred_at=started_at,
                    )
                ],
            )
            self._append_queue_position_events_for_queued_jobs(started_at)
            # notify() may wake an unrelated stream; extra notify_all() wake-ups are acceptable because pending jobs are bounded.
            self._changed.notify_all()
            return claimed

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
        with self._changed:
            record = self._record(job.id)
            if record.job.revision != expected_revision:
                raise StoreWriteConflictError(f"Job revision changed: {job.id}")
            was_queued = record.job.state == JobState.QUEUED
            updated_job = replace(job, revision=expected_revision + 1, queue_position=None)
            record.job = updated_job
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
    ) -> Iterator[JobEvent | JobReplayError | JobReplayGap | None]:
        """Yield events after the requested ID until the job becomes terminal.

        Iteration blocks up to the keepalive interval when no newer event exists.
        Yield `None` when the keepalive interval passes without a new event.

        Raises:
            JobNotFoundError: If the job does not exist or is deleted while streaming.
        """
        replay_error: JobReplayError | None = None
        replay_gap: JobReplayGap | None = None
        with self._changed:
            record = self._record(job_id)
            if after_id is None:
                last_seen = 0
            else:
                parsed_id = self._parse_event_id(after_id)
                oldest_retained_event_id = record.events[0].id if record.events else None
                newest_retained_event_id = record.events[-1].id if record.events else None
                if parsed_id is None:
                    replay_error = JobReplayError(
                        code="malformed_cursor",
                        requested_last_event_id=after_id,
                        oldest_retained_event_id=oldest_retained_event_id,
                        newest_retained_event_id=newest_retained_event_id,
                    )
                elif newest_retained_event_id is not None and parsed_id > int(newest_retained_event_id):
                    replay_error = JobReplayError(
                        code="future_cursor",
                        requested_last_event_id=after_id,
                        oldest_retained_event_id=oldest_retained_event_id,
                        newest_retained_event_id=newest_retained_event_id,
                    )
                elif not any(event.id == after_id for event in record.events):
                    replay_gap = JobReplayGap(
                        requested_last_event_id=after_id,
                        oldest_retained_event_id=oldest_retained_event_id,
                        replay_checkpoint_id=newest_retained_event_id,
                        job=self._with_queue_position(record.job),
                    )
                    last_seen = int(newest_retained_event_id) if newest_retained_event_id is not None else 0
                else:
                    last_seen = parsed_id

        if replay_error is not None:
            yield replay_error
            return
        if replay_gap is not None:
            yield replay_gap

        while True:
            with self._changed:
                record = self._record(job_id)
                available = [event for event in record.events if int(event.id) > last_seen]
                if not available and not record.job.state.terminal:
                    self._changed.wait(timeout=keepalive_seconds)
                    record = self._record(job_id)
                    available = [event for event in record.events if int(event.id) > last_seen]
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
                last_seen = int(event.id)
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

    def find_claimed_before(self, cutoff: datetime) -> list[Job]:
        """Return active jobs whose worker claim expired by the cutoff.

        Maintenance terminates them because their worker is presumed lost.
        """
        with self._lock:
            return [
                self._with_queue_position(record.job)
                for record in self._records.values()
                if record.job.state in {JobState.RUNNING, JobState.CANCELLING}
                and record.job.claim_expires_at is not None
                and record.job.claim_expires_at <= cutoff
            ]

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
    def _parse_event_id(value: str) -> int | None:
        """Parse a canonical memory-store event ID generated by this store."""
        if not value.isascii() or not value.isdecimal() or value.startswith("0"):
            return None
        return int(value)

    @staticmethod
    def _with_initial_queue_position(
        events: Sequence[JobEvent],
        queue_position: int | None,
    ) -> list[JobEvent]:
        """Add the initial queue position to queued state events."""
        return [
            replace(event, data={**event.data, "queue_position": queue_position})
            if event.type == JobEventType.STATE_CHANGED and event.data.get("state") == JobState.QUEUED.value
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
                        type=JobEventType.STATE_CHANGED,
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
