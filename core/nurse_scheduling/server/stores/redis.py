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
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, overload
from uuid import uuid4

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
    JobFailure,
    JobRequest,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    ServerActivity,
    StoredArtifact,
    StoreLimits,
)
from ..retry import retry_with_backoff


SOCKET_TIMEOUT_MARGIN_SECONDS = 5.0
"""Additional socket time allowed beyond one blocking event-stream read."""
REDIS_OPERATION_TIMEOUT_SECONDS = 2.0
"""Short timeout for ordinary Redis operations and deployment probes."""


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
        # Bound ordinary Redis waits without inheriting the longer timeout
        # required by blocking event-stream reads.
        self._redis = redis.Redis.from_url(
            url,
            decode_responses=False,
            socket_connect_timeout=REDIS_OPERATION_TIMEOUT_SECONDS,
            socket_timeout=REDIS_OPERATION_TIMEOUT_SECONDS,
        )
        """Binary-safe Redis client for bounded ordinary operations."""
        self._stream_redis = redis.Redis.from_url(
            url,
            decode_responses=False,
            socket_connect_timeout=REDIS_OPERATION_TIMEOUT_SECONDS,
            socket_timeout=event_stream_keepalive_seconds + SOCKET_TIMEOUT_MARGIN_SECONDS,
        )
        """Redis client whose read timeout exceeds one blocking event-stream read."""
        self._redis.ping()
        self._store_id_key = self._key("metadata:store_id")
        """Persistent UUID identifying this Redis database and key namespace."""
        self._store_id = self._resolve_store_id()
        """Persistent identity captured during startup."""
        self._jobs_key = self._key("jobs")
        """Sorted-set key (`ZADD`) of retained job IDs scored by creation time."""
        self._pending_key = self._key("pending")
        """Set key (`SADD`) of non-terminal job IDs used for pending-capacity checks."""
        self._queue_key = self._key("queue")
        """Sorted-set key (`ZADD`) of queued job IDs scored by creation time for FIFO claims."""
        self._workers_key = self._key("workers", "leases")
        """Sorted-set key of worker IDs scored by lease expiration time."""
        self._worker_active_jobs_key = self._key("workers", "active")
        """Hash mapping worker IDs to their exclusively owned active job IDs."""

    @property
    def store_id(self) -> str:
        """Return the persistent identity of this Redis database and namespace."""
        return self._store_id

    def _resolve_store_id(self) -> str:
        """Atomically create or read the persistent Redis store identity."""
        return retry_with_backoff(
            self._resolve_store_id_once,
            retry_on=redis.RedisError,
        )

    def _resolve_store_id_once(self) -> str:
        """Create or read the store identity in one retryable attempt."""
        value = _decode(self._redis.get(self._store_id_key))
        if isinstance(value, str) and value.strip():
            return value
        candidate = str(uuid4())
        self._redis.set(self._store_id_key, candidate, nx=True)
        value = _decode(self._redis.get(self._store_id_key))
        if isinstance(value, str) and value.strip():
            return value
        raise redis.RedisError("Redis job store identity could not be initialized")

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

    def claim_next_job(
        self,
        worker_id: str,
        started_at: datetime,
        runtime_identity: Mapping[str, str] | None = None,
    ) -> Job | None:
        """Atomically assign the oldest queued job to a worker.

        Return the claimed running job, or `None` when the queue is empty.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(self._queue_key, self._workers_key, self._worker_active_jobs_key)
                    worker_expiry = transaction.zscore(self._workers_key, worker_id)
                    active_job_id = _decode(transaction.hget(self._worker_active_jobs_key, worker_id))
                    if worker_expiry is None or worker_expiry <= started_at.timestamp() or active_job_id is not None:
                        transaction.unwatch()
                        return None
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
                        revision=current.revision + 1,
                        queue_position=None,
                    )
                    event = JobEvent(
                        type="job.state_changed",
                        data={
                            "state": JobState.RUNNING.value,
                            "queue_position": None,
                            "cancel_requested": False,
                            "early_completion_requested": False,
                            "worker_id": worker_id,
                            **({"runtime": dict(runtime_identity)} if runtime_identity is not None else {}),
                        },
                        occurred_at=started_at,
                    )
                    remaining_ids = [_decode(raw_id) for raw_id in transaction.zrange(self._queue_key, 1, -1)]
                    transaction.multi()
                    transaction.set(job_key, self._serialize_job(claimed))
                    transaction.zrem(self._queue_key, job_id)
                    transaction.hset(self._worker_active_jobs_key, worker_id, job_id)
                    self._stage_event_appends(transaction, job_id, [event])
                    self._stage_queue_position_events(transaction, remaining_ids, started_at)
                    transaction.execute()
                return claimed
            except redis.WatchError:
                continue

    def register_worker(self, worker_id: str, registered_at: datetime, lease_expires_at: datetime) -> bool:
        """Register an idle worker without overwriting live or unresolved ownership."""
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(self._workers_key, self._worker_active_jobs_key)
                    current_expiry = transaction.zscore(self._workers_key, worker_id)
                    active_job_id = transaction.hget(self._worker_active_jobs_key, worker_id)
                    if (
                        current_expiry is not None and current_expiry > registered_at.timestamp()
                    ) or active_job_id is not None:
                        transaction.unwatch()
                        return False
                    transaction.multi()
                    transaction.zadd(self._workers_key, {worker_id: lease_expires_at.timestamp()})
                    transaction.hdel(self._worker_active_jobs_key, worker_id)
                    transaction.execute()
                    return True
            except redis.WatchError:
                continue

    def renew_worker(self, worker_id: str, renewed_at: datetime, lease_expires_at: datetime) -> bool:
        """Renew a worker lease only while its current lease is unexpired."""
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(self._workers_key)
                    current_expiry = transaction.zscore(self._workers_key, worker_id)
                    if current_expiry is None or current_expiry <= renewed_at.timestamp():
                        transaction.unwatch()
                        return False
                    transaction.multi()
                    transaction.zadd(self._workers_key, {worker_id: lease_expires_at.timestamp()})
                    transaction.execute()
                    return True
            except redis.WatchError:
                continue

    def unregister_worker(self, worker_id: str) -> None:
        """Remove worker presence and its active-job association."""
        with self._redis.pipeline() as transaction:
            transaction.zrem(self._workers_key, worker_id)
            transaction.hdel(self._worker_active_jobs_key, worker_id)
            transaction.execute()

    def worker_owns_job(self, worker_id: str, job_id: str, observed_at: datetime) -> bool:
        """Return whether a live worker lease points to the supplied job."""
        with self._redis.pipeline() as transaction:
            transaction.zscore(self._workers_key, worker_id)
            transaction.hget(self._worker_active_jobs_key, worker_id)
            current_expiry, active_job_id = transaction.execute()
        return bool(
            current_expiry is not None and current_expiry > observed_at.timestamp() and _decode(active_job_id) == job_id
        )

    def get_activity(self, observed_at: datetime) -> ServerActivity:
        """Return aggregate current job states and unexpired worker leases."""
        raw_ids = self._redis.smembers(self._pending_key)
        raw_jobs = self._redis.mget([self._job_key(_decode(raw_id)) for raw_id in raw_ids]) if raw_ids else []
        states = [self._deserialize_job(raw).state for raw in raw_jobs if raw is not None]
        online_workers = self._redis.zcount(self._workers_key, f"({observed_at.timestamp()}", "+inf")
        return ServerActivity(
            queued_jobs=states.count(JobState.QUEUED),
            running_jobs=states.count(JobState.RUNNING),
            cancelling_jobs=states.count(JobState.CANCELLING),
            online_workers=online_workers,
        )

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
                    worker_id_to_release: str | None = None
                    if updated_job.state.terminal and updated_job.worker_id is not None:
                        transaction.watch(self._worker_active_jobs_key)
                        active_job_id = _decode(transaction.hget(self._worker_active_jobs_key, updated_job.worker_id))
                        if active_job_id == updated_job.id:
                            worker_id_to_release = updated_job.worker_id
                    transaction.multi()
                    transaction.set(job_key, self._serialize_job(updated_job))
                    if updated_job.state != JobState.QUEUED:
                        transaction.zrem(self._queue_key, updated_job.id)
                    if updated_job.state.terminal:
                        transaction.srem(self._pending_key, updated_job.id)
                    if worker_id_to_release is not None:
                        transaction.hdel(self._worker_active_jobs_key, worker_id_to_release)
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
    ) -> Iterator[JobEvent | None]:
        """Yield events after the requested ID until the job becomes terminal.

        Iteration blocks up to the keepalive interval when no newer event exists.
        Yield `None` when the keepalive interval passes without a new event.

        Raises:
            JobNotFoundError: If the job does not exist or is deleted while streaming.
            redis.RedisError: If a Redis operation fails.
        """
        self.get(job_id)
        last_id = after_id or "0-0"
        block_ms = max(1, int(keepalive_seconds * 1000))
        while True:
            terminal = self.get(job_id).state.terminal
            try:
                streams = self._stream_redis.xread(
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

    def find_finished_before(self, cutoff: datetime) -> list[Job]:
        """Return jobs finished before the retention cutoff.

        Maintenance deletes them to keep retained job history bounded.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        return [job for job in self._all_jobs() if job.finished_at is not None and job.finished_at < cutoff]

    def find_jobs_without_live_workers(self, observed_at: datetime) -> list[Job]:
        """Return active jobs without a matching live worker association.

        Maintenance terminates them because their worker is presumed lost.

        Raises:
            redis.RedisError: If a Redis operation fails.
        """
        return [
            job
            for job in self._all_jobs()
            if job.state in {JobState.RUNNING, JobState.CANCELLING}
            and (job.worker_id is None or not self.worker_owns_job(job.worker_id, job.id, observed_at))
        ]

    def remove_expired_worker_leases(self, observed_at: datetime) -> list[str]:
        """Atomically remove worker leases that cannot be renewed anymore."""
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(self._workers_key, self._worker_active_jobs_key)
                    raw_ids = transaction.zrangebyscore(
                        self._workers_key,
                        "-inf",
                        observed_at.timestamp(),
                    )
                    worker_ids = [_decode(raw_id) for raw_id in raw_ids]
                    if not worker_ids:
                        transaction.unwatch()
                        return []
                    transaction.multi()
                    transaction.zrem(self._workers_key, *worker_ids)
                    transaction.hdel(self._worker_active_jobs_key, *worker_ids)
                    transaction.execute()
                    return worker_ids
            except redis.WatchError:
                continue

    def check_health(self) -> None:
        """Raise an error when Redis is unavailable or its identity changed.

        Raises:
            redis.RedisError: If the Redis health check fails.
        """
        # GET verifies connectivity and store identity in one bounded command.
        # Avoid PING and retries so readiness uses one bounded Redis operation.
        resolved_store_id = _decode(self._redis.get(self._store_id_key))
        if resolved_store_id != self._store_id:
            raise redis.RedisError("Redis job store identity changed")

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
            if event.type == "job.state_changed" and event.data.get("state") == JobState.QUEUED.value
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
