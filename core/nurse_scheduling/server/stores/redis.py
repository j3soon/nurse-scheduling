"""Redis implementation of the optimization job store contract."""

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

import json
import math
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, overload

import redis

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
    JobFailure,
    JobRequest,
    JobReplayError,
    JobReplayGap,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
)


SOCKET_TIMEOUT_MARGIN_SECONDS = 5.0
"""Additional socket time allowed beyond one blocking event-stream read."""


@overload
def _decode(value: bytes | str) -> str: ...


@overload
def _decode(value: None) -> None: ...


def _decode(value: bytes | str | None) -> str | None:
    """Normalize an optional Redis value to text.

    Raises:
        UnicodeDecodeError: If a byte value is not valid UTF-8.
    """
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else value


class RedisJobStore:
    """Store jobs, queue state, events, input, and artifacts in Redis."""

    def __init__(
        self,
        *,
        url: str,
        key_prefix: str,
        event_stream_keepalive_seconds: float = 10.0,
        max_events_per_job: int = 1_000,
    ):
        """Connect to Redis and initialize namespaced index keys.

        Raises:
            ValueError: If a connection setting or the key prefix is invalid.
            redis.RedisError: If Redis cannot be reached.
        """
        self._prefix = key_prefix.rstrip(":")
        """Namespace that isolates this store's keys from other applications."""
        if not self._prefix:
            raise ValueError("JOB_REDIS_KEY_PREFIX must not be empty")
        if not math.isfinite(event_stream_keepalive_seconds) or event_stream_keepalive_seconds <= 0:
            raise ValueError("event_stream_keepalive_seconds must be positive")
        if max_events_per_job <= 0:
            raise ValueError("max_events_per_job must be positive")
        self._max_events_per_job = max_events_per_job
        """Maximum entries retained in each replayable event stream."""
        self._redis = redis.Redis.from_url(
            url,
            decode_responses=False,
            socket_timeout=event_stream_keepalive_seconds + SOCKET_TIMEOUT_MARGIN_SECONDS,
        )
        """Binary-safe Redis client shared by all store operations."""
        self._redis.ping()
        self._jobs_key = self._key("jobs")
        """Sorted-set key (`ZADD`) of retained job IDs scored by creation time."""
        self._pending_key = self._key("pending")
        """Set key (`SADD`) of non-terminal job IDs used for pending-capacity checks."""
        self._queue_key = self._key("queue")
        """Sorted-set key (`ZADD`) of queued job IDs scored by creation time for FIFO claims."""

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
            redis.RedisError: If a Redis operation fails.
        """
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    job_key = self._job_key(job.id)
                    transaction.watch(self._jobs_key, self._pending_key, self._queue_key, job_key)
                    if transaction.exists(job_key):
                        transaction.unwatch()
                        raise StoreWriteConflictError(f"Job already exists: {job.id}")
                    pending_count = transaction.scard(self._pending_key)
                    if pending_count >= limits.max_pending:
                        transaction.unwatch()
                        raise JobCapacityError("Too many jobs are queued or running")

                    prune_ids: list[str] = []
                    retained_count = transaction.zcard(self._jobs_key)
                    if retained_count >= limits.max_retained:
                        terminal = sorted(
                            (candidate for candidate in self._all_jobs() if candidate.state.terminal),
                            key=lambda candidate: candidate.finished_at or candidate.created_at,
                        )
                        prune_count = retained_count - limits.max_retained + 1
                        if len(terminal) < prune_count:
                            transaction.unwatch()
                            raise JobCapacityError("Too many jobs are retained")
                        prune_ids = [candidate.id for candidate in terminal[:prune_count]]

                    queued_entries = transaction.zrange(self._queue_key, 0, -1, withscores=True)
                    queue_order = [(_decode(raw_id), score) for raw_id, score in queued_entries]
                    # can bisect to insert but just sort for simplicity
                    queue_order.append((job.id, job.created_at.timestamp()))
                    queue_order.sort(key=lambda entry: (entry[1], entry[0]))
                    queue_position = next(
                        index for index, (queued_id, _score) in enumerate(queue_order, start=1) if queued_id == job.id
                    )

                    saved = replace(job, revision=1, queue_position=None)
                    transaction.multi()
                    for prune_id in prune_ids:
                        self._stage_job_deletion(transaction, prune_id)
                    transaction.set(job_key, self._serialize_job(saved))
                    transaction.set(self._input_key(job.id), input_bytes)
                    transaction.zadd(self._jobs_key, {job.id: job.created_at.timestamp()})
                    transaction.zadd(self._queue_key, {job.id: job.created_at.timestamp()})
                    transaction.sadd(self._pending_key, job.id)
                    self._stage_event_appends(
                        transaction,
                        job.id,
                        self._with_initial_queue_position(events, queue_position),
                    )
                    for position, (queued_id, _score) in enumerate(queue_order, start=1):
                        if queued_id != job.id:
                            self._stage_queue_position_event(transaction, queued_id, position, job.created_at)
                    transaction.execute()
                return self.get(job.id)
            except redis.WatchError:
                continue

    def get(self, job_id: str) -> Job:
        """Return a job snapshot with its current queue position.

        Raises:
            JobNotFoundError: If the job does not exist.
            redis.RedisError: If a Redis operation fails.
        """
        raw = self._redis.get(self._job_key(job_id))
        if raw is None:
            raise JobNotFoundError("Job was not found")
        return self._with_queue_position(self._deserialize_job(raw))

    def get_input(self, job_id: str) -> bytes:
        """Return the original input submitted for a job.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobInputNotFoundError: If the job has no stored input.
            redis.RedisError: If a Redis operation fails.
        """
        if not self._redis.exists(self._job_key(job_id)):
            raise JobNotFoundError("Job was not found")
        content = self._redis.get(self._input_key(job_id))
        if content is None:
            raise JobInputNotFoundError("Job input was not found")
        return content

    def get_artifact(self, job_id: str, name: str) -> StoredArtifact:
        """Return the named artifact stored for a job.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobArtifactNotFoundError: If the named artifact does not exist.
            redis.RedisError: If a Redis operation fails.
        """
        job = self.get(job_id)
        if job.artifact_name != name:
            raise JobArtifactNotFoundError("Job artifact was not found")
        content = self._redis.get(self._artifact_key(job_id))
        if content is None:
            raise JobArtifactNotFoundError("Job artifact was not found")
        metadata = self._redis.hgetall(self._artifact_metadata_key(job_id))
        stored_name = _decode(metadata.get(b"name")) or name
        media_type = _decode(metadata.get(b"media_type")) or "application/octet-stream"
        return StoredArtifact(name=stored_name, media_type=media_type, content=content)

    def claim_next(self, worker_id: str, started_at: datetime, claim_expires_at: datetime) -> Job | None:
        """Atomically assign the oldest queued job to a worker.

        Return the claimed running job, or `None` when the queue is empty.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(self._queue_key)
                    queued = transaction.zrange(self._queue_key, 0, 0)
                    if not queued:
                        transaction.unwatch()
                        return None
                    job_id = _decode(queued[0])
                    job_key = self._job_key(job_id)
                    transaction.watch(job_key)
                    raw = transaction.get(job_key)
                    if raw is None:
                        # Simply continuing would suffice if a normal transaction removed this job.
                        # Remove the orphan defensively in case the stored data is inconsistent,
                        # so it cannot block later claims.
                        transaction.multi()
                        transaction.zrem(self._queue_key, job_id)
                        transaction.execute()
                        continue
                    current = self._deserialize_job(raw)
                    if current.state != JobState.QUEUED:
                        # Another worker may have claimed the job after this queue read.
                        # Simply continuing would suffice for that normal race. Remove the entry
                        # defensively if its state and queue index are inconsistent, so it cannot
                        # block later claims.
                        transaction.multi()
                        transaction.zrem(self._queue_key, job_id)
                        transaction.execute()
                        continue
                    claimed = replace(
                        current,
                        state=JobState.RUNNING,
                        started_at=started_at,
                        worker_id=worker_id,
                        claim_expires_at=claim_expires_at,
                        revision=current.revision + 1,
                        queue_position=None,
                    )
                    event = JobEvent(
                        type=JobEventType.STATE_CHANGED,
                        data={
                            "state": JobState.RUNNING.value,
                            "queue_position": None,
                            "cancel_requested": False,
                            "early_completion_requested": False,
                        },
                        occurred_at=started_at,
                    )
                    remaining_ids = [_decode(raw_id) for raw_id in transaction.zrange(self._queue_key, 1, -1)]
                    transaction.multi()
                    transaction.set(job_key, self._serialize_job(claimed))
                    transaction.zrem(self._queue_key, job_id)
                    self._stage_event_appends(transaction, job_id, [event])
                    self._stage_queue_position_events(transaction, remaining_ids, started_at)
                    transaction.execute()
                return claimed
            except redis.WatchError:
                continue

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
            redis.RedisError: If a Redis operation fails.
        """
        job_key = self._job_key(job.id)
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(job_key)
                    raw = transaction.get(job_key)
                    if raw is None:
                        transaction.unwatch()
                        raise JobNotFoundError("Job was not found")
                    current = self._deserialize_job(raw)
                    if current.revision != expected_revision:
                        transaction.unwatch()
                        raise StoreWriteConflictError(f"Job revision changed: {job.id}")
                    updated_job = replace(job, revision=expected_revision + 1, queue_position=None)
                    remaining_queue_ids: list[str] = []
                    if current.state == JobState.QUEUED and updated_job.state != JobState.QUEUED:
                        transaction.watch(self._queue_key)
                        remaining_queue_ids = [
                            queued_id
                            for raw_id in transaction.zrange(self._queue_key, 0, -1)
                            if (queued_id := _decode(raw_id)) != updated_job.id
                        ]
                    transaction.multi()
                    transaction.set(job_key, self._serialize_job(updated_job))
                    if updated_job.state != JobState.QUEUED:
                        transaction.zrem(self._queue_key, updated_job.id)
                    if updated_job.state.terminal:
                        transaction.srem(self._pending_key, updated_job.id)
                    if artifact is not None:
                        transaction.set(self._artifact_key(updated_job.id), artifact.content)
                        transaction.hset(
                            self._artifact_metadata_key(updated_job.id),
                            mapping={"name": artifact.name, "media_type": artifact.media_type},
                        )
                    self._stage_event_appends(transaction, updated_job.id, events)
                    if remaining_queue_ids:
                        occurred_at = events[-1].occurred_at if events else datetime.now(updated_job.created_at.tzinfo)
                        self._stage_queue_position_events(transaction, remaining_queue_ids, occurred_at)
                    transaction.execute()
                return self.get(updated_job.id)
            except redis.WatchError:
                continue

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
            redis.RedisError: If a Redis operation fails.
        """
        last_id, replay_error, replay_gap = self._resolve_event_cursor(job_id, after_id)
        if replay_error is not None:
            yield replay_error
            return
        if replay_gap is not None:
            yield replay_gap
        block_ms = max(1, int(keepalive_seconds * 1000))
        while True:
            terminal = self.get(job_id).state.terminal
            try:
                streams = self._redis.xread(
                    {self._events_key(job_id): last_id},
                    block=None if terminal else block_ms,
                )
            except redis.exceptions.TimeoutError:
                streams = []
            if not streams:
                if terminal:
                    return
                yield None
                continue
            for _stream, entries in streams:
                for raw_id, fields in entries:
                    last_id = _decode(raw_id)
                    yield JobEvent(
                        id=last_id,
                        type=_decode(fields.get(b"type")) or "job.event",
                        data=json.loads(_decode(fields.get(b"data")) or "{}"),
                        occurred_at=datetime.fromisoformat(_decode(fields.get(b"occurred_at")) or ""),
                    )
            if terminal or self.get(job_id).state.terminal:
                return

    def _resolve_event_cursor(
        self,
        job_id: str,
        after_id: str | None,
    ) -> tuple[str, JobReplayError | None, JobReplayGap | None]:
        """Resolve a cursor to a replay position, replay error, or replay gap."""
        parsed_id = self._parse_event_id(after_id) if after_id is not None else None
        events_key = self._events_key(job_id)
        with self._redis.pipeline(transaction=True) as transaction:
            transaction.get(self._job_key(job_id))
            transaction.zrank(self._queue_key, job_id)
            transaction.xrange(events_key, min="-", max="+", count=1)
            transaction.xrevrange(events_key, max="+", min="-", count=1)
            if parsed_id is not None:
                transaction.xrange(events_key, min=after_id, max=after_id, count=1)
            results = transaction.execute()

        raw_job, queue_rank, oldest_entries, newest_entries, *exact_results = results
        if raw_job is None:
            raise JobNotFoundError("Job was not found")
        job = self._deserialize_job(raw_job)
        if job.state == JobState.QUEUED:
            job = replace(job, queue_position=queue_rank + 1 if queue_rank is not None else None)
        oldest_retained_event_id = _decode(oldest_entries[0][0]) if oldest_entries else None
        newest_retained_event_id = _decode(newest_entries[0][0]) if newest_entries else None

        if after_id is None:
            return "0-0", None, None
        if parsed_id is None:
            return (
                "0-0",
                JobReplayError(
                    code="malformed_cursor",
                    requested_last_event_id=after_id,
                    oldest_retained_event_id=oldest_retained_event_id,
                    newest_retained_event_id=newest_retained_event_id,
                ),
                None,
            )

        exact_entries = exact_results[0] if exact_results else []
        newest_retained_id = self._parse_event_id(newest_retained_event_id)
        if newest_retained_id is not None and parsed_id > newest_retained_id:
            return (
                "0-0",
                JobReplayError(
                    code="future_cursor",
                    requested_last_event_id=after_id,
                    oldest_retained_event_id=oldest_retained_event_id,
                    newest_retained_event_id=newest_retained_event_id,
                ),
                None,
            )
        if not exact_entries:
            return (
                newest_retained_event_id or "0-0",
                None,
                JobReplayGap(
                    requested_last_event_id=after_id,
                    oldest_retained_event_id=oldest_retained_event_id,
                    replay_checkpoint_id=newest_retained_event_id,
                    job=job,
                ),
            )
        return after_id, None, None

    @staticmethod
    def _parse_event_id(value: str | None) -> tuple[int, int] | None:
        """Parse a canonical Redis stream ID generated by this store."""
        if value is None:
            return None
        parts = value.split("-")
        if len(parts) != 2 or any(not part or not part.isascii() or not part.isdecimal() for part in parts):
            return None
        parsed = (int(parts[0]), int(parts[1]))
        if parsed == (0, 0) or value != f"{parsed[0]}-{parsed[1]}":
            return None
        return parsed

    def find_finished_before(self, cutoff: datetime) -> list[Job]:
        """Return jobs finished before the retention cutoff.

        Maintenance deletes them to keep retained job history bounded.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        return [job for job in self._all_jobs() if job.finished_at is not None and job.finished_at < cutoff]

    def find_claimed_before(self, cutoff: datetime) -> list[Job]:
        """Return active jobs whose worker claim expired by the cutoff.

        Maintenance terminates them because their worker is presumed lost.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        return [
            job
            for job in self._all_jobs()
            if job.state in {JobState.RUNNING, JobState.CANCELLING}
            and job.claim_expires_at is not None
            and job.claim_expires_at <= cutoff
        ]

    def check_health(self) -> None:
        """Raise an error when Redis is unavailable.

        Raises:
            redis.RedisError: If the Redis health check fails.
        """
        self._redis.ping()

    def delete(self, job_id: str, expected_revision: int) -> None:
        """Delete a job and its Redis data if its revision still matches.

        Raises:
            JobNotFoundError: If the job does not exist.
            StoreWriteConflictError: If the stored revision no longer matches.
            redis.RedisError: If a Redis operation fails.
        """
        job_key = self._job_key(job_id)
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(job_key)
                    raw = transaction.get(job_key)
                    if raw is None:
                        transaction.unwatch()
                        raise JobNotFoundError("Job was not found")
                    current = self._deserialize_job(raw)
                    if current.revision != expected_revision:
                        transaction.unwatch()
                        raise StoreWriteConflictError(f"Job revision changed: {job_id}")
                    transaction.multi()
                    self._stage_job_deletion(transaction, job_id)
                    transaction.execute()
                return
            except redis.WatchError:
                continue

    def _all_jobs(self) -> list[Job]:
        """Return all jobs referenced by the retained-jobs index.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        raw_ids = self._redis.zrange(self._jobs_key, 0, -1)
        job_ids = [_decode(raw_id) for raw_id in raw_ids]
        if not job_ids:
            return []
        raw_jobs = self._redis.mget([self._job_key(job_id) for job_id in job_ids])
        return [self._deserialize_job(raw) for raw in raw_jobs if raw is not None]

    def _with_queue_position(self, job: Job) -> Job:
        """Return a job copy with its position derived from the Redis queue.

        Raises:
            redis.RedisError: If the queue rank cannot be read.
        """
        if job.state != JobState.QUEUED:
            return replace(job, queue_position=None)
        rank = self._redis.zrank(self._queue_key, job.id)
        return replace(job, queue_position=rank + 1 if rank is not None else None)

    def _stage_event_appends(self, transaction, job_id: str, events: Sequence[JobEvent]) -> None:
        """Stage event-stream appends in an active Redis transaction."""
        for event in events:
            transaction.xadd(
                self._events_key(job_id),
                {
                    "type": event.type,
                    "data": json.dumps(event.data, separators=(",", ":")),  # eliminate whitespace for compact storage
                    "occurred_at": event.occurred_at.isoformat(),
                },
                maxlen=self._max_events_per_job,
                approximate=False,
            )

    def _stage_job_deletion(self, transaction, job_id: str) -> None:
        """Stage deletion of all job data and indexes in an active Redis transaction."""
        transaction.delete(
            self._job_key(job_id),
            self._input_key(job_id),
            self._artifact_key(job_id),
            self._artifact_metadata_key(job_id),
            self._events_key(job_id),
        )
        transaction.zrem(self._jobs_key, job_id)
        transaction.zrem(self._queue_key, job_id)
        transaction.srem(self._pending_key, job_id)

    @staticmethod
    def _serialize_job(job: Job) -> str:
        """Serialize a job to the compact JSON representation stored in Redis."""
        data: dict[str, Any] = {
            "id": job.id,
            "state": job.state.value,
            "request": {
                "input_name": job.request.input_name,
                "client_id": job.request.client_id,
                "solver": job.request.solver,
                "prettify": job.request.prettify,
                "timeout_seconds": job.request.timeout_seconds,
            },
            "created_at": job.created_at.isoformat(),
            "revision": job.revision,
            "started_at": job.started_at.isoformat() if job.started_at is not None else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at is not None else None,
            "worker_id": job.worker_id,
            "claim_expires_at": job.claim_expires_at.isoformat() if job.claim_expires_at is not None else None,
            "result": (
                {
                    "outcome": job.result.outcome.value,
                    "score": job.result.score,
                    "solver_status": job.result.solver_status,
                    "termination_reason": job.result.termination_reason,
                }
                if job.result is not None
                else None
            ),
            "failure": (
                {"code": job.failure.code, "message": job.failure.message} if job.failure is not None else None
            ),
            "cancel_requested": job.cancel_requested,
            "early_completion_requested": job.early_completion_requested,
            "artifact_name": job.artifact_name,
        }
        return json.dumps(data, separators=(",", ":"))

    @staticmethod
    def _deserialize_job(raw: bytes | str) -> Job:
        """Deserialize a stored JSON value into a job model."""
        data = json.loads(_decode(raw))
        request = data["request"]
        result = data.get("result")
        failure = data.get("failure")
        return Job(
            id=data["id"],
            state=JobState(data["state"]),
            request=JobRequest(
                input_name=request["input_name"],
                client_id=request["client_id"],
                solver=request["solver"],
                prettify=request.get("prettify"),
                timeout_seconds=request["timeout_seconds"],
            ),
            created_at=datetime.fromisoformat(data["created_at"]),
            revision=data["revision"],
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            worker_id=data.get("worker_id"),
            claim_expires_at=(
                datetime.fromisoformat(data["claim_expires_at"]) if data.get("claim_expires_at") else None
            ),
            result=(
                OptimizationResult(
                    outcome=OptimizationOutcome(result["outcome"]),
                    score=result.get("score"),
                    solver_status=result["solver_status"],
                    termination_reason=result.get("termination_reason"),
                )
                if result is not None
                else None
            ),
            failure=JobFailure(**failure) if failure is not None else None,
            cancel_requested=bool(data.get("cancel_requested", False)),
            early_completion_requested=bool(data.get("early_completion_requested", False)),
            artifact_name=data.get("artifact_name"),
        )

    def _key(self, *parts: str) -> str:
        """Build a Redis key beneath the configured namespace."""
        return ":".join((self._prefix, *parts))

    def _job_key(self, job_id: str) -> str:
        """Return the string key (`SET`) containing serialized job metadata."""
        return self._key("job", job_id)

    def _input_key(self, job_id: str) -> str:
        """Return the string key (`SET`) containing the submitted input bytes."""
        return self._key("job", job_id, "input")

    def _artifact_key(self, job_id: str) -> str:
        """Return the string key (`SET`) containing the generated artifact bytes."""
        return self._key("job", job_id, "artifact")

    def _artifact_metadata_key(self, job_id: str) -> str:
        """Return the hash key (`HSET`) containing the artifact name and media type."""
        return self._key("job", job_id, "artifact_metadata")

    def _events_key(self, job_id: str) -> str:
        """Return the stream key (`XADD`) containing persisted job events."""
        return self._key("job", job_id, "events")

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

    def _stage_queue_position_events(self, transaction, job_ids: Sequence[str], occurred_at: datetime) -> None:
        """Stage position events for an ordered sequence of queued jobs in an active Redis transaction."""
        for position, job_id in enumerate(job_ids, start=1):
            self._stage_queue_position_event(transaction, job_id, position, occurred_at)

    def _stage_queue_position_event(
        self,
        transaction,
        job_id: str,
        position: int,
        occurred_at: datetime,
    ) -> None:
        """Stage one job state event with its updated queue position in an active Redis transaction."""
        self._stage_event_appends(
            transaction,
            job_id,
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
