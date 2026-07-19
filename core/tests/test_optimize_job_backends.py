"""Shared contract tests for memory and Redis job stores."""

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

# This test is mostly AI generated.

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, call

import fakeredis
import pytest
import redis

from nurse_scheduling.server.config import DEFAULT_JOB_RETENTION_SECONDS, DEFAULT_MAX_RETAINED_JOBS
from nurse_scheduling.server.errors import (
    JobArtifactNotFoundError,
    JobCapacityError,
    JobInputNotFoundError,
    JobNotFoundError,
    StoreWriteConflictError,
)
from nurse_scheduling.server.jobs.controller import JobController, utc_now
from nurse_scheduling.server.jobs.models import (
    JobFailure,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
)
from nurse_scheduling.server.retry import DEFAULT_RETRY_MAX_ATTEMPTS
from nurse_scheduling.server.stores.memory import MemoryJobStore


def _redis_url() -> str | None:
    return os.getenv("JOB_REDIS_TEST_URL") or os.getenv("JOB_REDIS_URL")


def _delete_redis_prefix(url: str, prefix: str) -> None:
    redis = pytest.importorskip("redis")
    client = redis.Redis.from_url(url)
    keys = list(client.scan_iter(f"{prefix}:*"))
    if keys:
        client.delete(*keys)


@pytest.fixture
def fake_redis_store_factory(monkeypatch):
    from nurse_scheduling.server.stores import redis as redis_store

    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        redis_store.redis.Redis,
        "from_url",
        lambda url, **kwargs: fakeredis.FakeRedis.from_url(url, server=server, **kwargs),
    )

    def create_store(**kwargs):
        key_prefix = kwargs.pop("key_prefix", f"nurse_scheduling:test:jobs:{uuid.uuid4().hex}")
        return redis_store.RedisJobStore(
            url="redis://localhost/0",
            key_prefix=key_prefix,
            **kwargs,
        )

    return create_store


@pytest.fixture(params=["memory", "fake-redis", "redis"])
def store_factory(request):
    if request.param == "memory":
        yield lambda **kwargs: MemoryJobStore(**kwargs)
        return
    if request.param == "fake-redis":
        yield request.getfixturevalue("fake_redis_store_factory")
        return
    url = _redis_url()
    if url is None:
        pytest.skip("Set JOB_REDIS_TEST_URL or JOB_REDIS_URL to run Redis store tests")
    redis = pytest.importorskip("redis")
    try:
        redis.Redis.from_url(url).ping()
    except redis.RedisError as error:
        pytest.skip(f"Redis is unavailable: {error}")
    from nurse_scheduling.server.stores.redis import RedisJobStore

    prefixes: list[str] = []

    def create_store(**kwargs):
        prefix = f"nurse_scheduling:test:jobs:{uuid.uuid4().hex}"
        prefixes.append(prefix)
        _delete_redis_prefix(url, prefix)
        return RedisJobStore(url=url, key_prefix=prefix, **kwargs)

    try:
        yield create_store
    finally:
        for prefix in prefixes:
            _delete_redis_prefix(url, prefix)


@pytest.fixture
def store(store_factory):
    return store_factory()


def _controller(store, *, max_pending=8, max_retained=32, now=None, runtime_identity=None):
    clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    sequence = iter(f"job_{index}" for index in range(100))
    return JobController(
        store,
        limits=StoreLimits(max_pending=max_pending, max_retained=max_retained),
        retention_seconds=60,
        claim_lease_seconds=30,
        runtime_identity=runtime_identity,
        clock=clock,
        id_factory=lambda: next(sequence),
    )


def _create(controller, input_name="input.yaml"):
    return controller.create_job(
        input_name=input_name,
        client_id="client",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"apiVersion: alpha\n",
    )


def _raise_watch_error_once(store, monkeypatch) -> None:
    original_pipeline = store._redis.pipeline
    error_pending = True

    class WatchErrorPipeline:
        def __init__(self, pipeline):
            self.pipeline = pipeline

        def __enter__(self):
            self.pipeline.__enter__()
            return self

        def __exit__(self, *args):
            return self.pipeline.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.pipeline, name)

        def execute(self):
            nonlocal error_pending
            if error_pending:
                error_pending = False
                raise redis.WatchError
            return self.pipeline.execute()

    monkeypatch.setattr(store._redis, "pipeline", lambda: WatchErrorPipeline(original_pipeline()))


def test_utc_now_returns_timezone_aware_utc_datetime():
    assert utc_now().tzinfo is timezone.utc


def test_redis_store_uses_default_connect_timeout_and_bounds_stream_reads(monkeypatch):
    from nurse_scheduling.server.stores import redis as redis_store

    operation_client = Mock()
    operation_client.get.return_value = b"existing-store-id"
    stream_client = Mock()
    from_url = Mock(side_effect=[operation_client, stream_client])
    monkeypatch.setattr(redis_store.redis.Redis, "from_url", from_url)

    store = redis_store.RedisJobStore(
        url="redis://redis.example/0",
        key_prefix="test:jobs",
        event_stream_keepalive_seconds=2.5,
    )

    assert from_url.call_args_list == [
        call(
            "redis://redis.example/0",
            decode_responses=False,
            socket_connect_timeout=redis_store.REDIS_OPERATION_TIMEOUT_SECONDS,
            socket_timeout=redis_store.REDIS_OPERATION_TIMEOUT_SECONDS,
        ),
        call(
            "redis://redis.example/0",
            decode_responses=False,
            socket_connect_timeout=redis_store.REDIS_OPERATION_TIMEOUT_SECONDS,
            socket_timeout=7.5,
        ),
    ]
    operation_client.ping.assert_called_once_with()

    operation_client.reset_mock()
    store.check_health()

    operation_client.get.assert_called_once_with(store._store_id_key)
    operation_client.ping.assert_not_called()


def test_redis_store_identity_is_shared_by_one_namespace(fake_redis_store_factory):
    prefix = f"nurse_scheduling:test:identity:{uuid.uuid4().hex}"

    with ThreadPoolExecutor(max_workers=8) as executor:
        shared = list(executor.map(lambda _index: fake_redis_store_factory(key_prefix=prefix), range(8)))
    separate = fake_redis_store_factory(key_prefix=f"{prefix}:separate")

    assert len({store.store_id for store in shared}) == 1
    assert shared[0].store_id != separate.store_id


def test_redis_store_health_rejects_identity_change(fake_redis_store_factory):
    store = fake_redis_store_factory()
    startup_store_id = store.store_id
    store._redis.set(store._store_id_key, "replacement-store-id")

    with pytest.raises(redis.RedisError, match="identity changed"):
        store.check_health()

    assert store.store_id == startup_store_id


def test_redis_store_health_does_not_retry_failed_identity_reads(fake_redis_store_factory, monkeypatch):
    store = fake_redis_store_factory()
    get = Mock(side_effect=redis.TimeoutError("timed out"))
    monkeypatch.setattr(store._redis, "get", get)

    with pytest.raises(redis.TimeoutError, match="timed out"):
        store.check_health()

    get.assert_called_once_with(store._store_id_key)


def test_redis_store_identity_failure_is_fatal_during_construction(monkeypatch):
    from nurse_scheduling.server.stores import redis as redis_store

    client = Mock()
    client.get.return_value = None
    monkeypatch.setattr(redis_store.redis.Redis, "from_url", Mock(return_value=client))
    monkeypatch.setattr("nurse_scheduling.server.retry.time.sleep", lambda _seconds: None)

    with pytest.raises(redis.RedisError, match="identity could not be initialized"):
        redis_store.RedisJobStore(url="redis://redis.example/0", key_prefix="test:jobs")

    assert client.get.call_count == DEFAULT_RETRY_MAX_ATTEMPTS * 2


def test_memory_store_identity_can_match_its_process_instance():
    store = MemoryJobStore(store_id="instance-123")

    assert store.store_id == "instance-123"


@pytest.mark.parametrize(
    "settings",
    [
        {"key_prefix": ":"},
        {"event_stream_keepalive_seconds": 0},
        {"event_stream_keepalive_seconds": float("inf")},
        {"max_events_per_job": 0},
    ],
)
def test_redis_store_rejects_invalid_configuration(settings):
    from nurse_scheduling.server.stores.redis import RedisJobStore

    configuration = {"url": "redis://localhost/0", "key_prefix": "test:jobs", **settings}
    with pytest.raises(ValueError):
        RedisJobStore(**configuration)


def test_memory_store_rejects_nonpositive_event_limit():
    with pytest.raises(ValueError, match="max_events_per_job must be positive"):
        MemoryJobStore(max_events_per_job=0)


def test_memory_store_rejects_empty_identity():
    with pytest.raises(ValueError, match="store_id must not be empty"):
        MemoryJobStore(store_id=" ")


def test_store_round_trips_lifecycle_input_events_and_artifact(store):
    runtime_identity = {
        "service_name": "nurse-scheduling-api",
        "api_version": "alpha",
        "app_version": "v-test",
        "deployment_id": "deployment-test",
        "instance_id": "instance-test",
        "started_at": datetime(2026, 7, 18, tzinfo=timezone.utc).isoformat(),
        "job_backend": "redis",
        "job_store_id": "store-test",
    }
    controller = _controller(store, runtime_identity=runtime_identity)
    created = _create(controller)
    assert created.state == JobState.QUEUED
    assert created.queue_position == 1
    assert controller.get_input(created.id) == b"apiVersion: alpha\n"

    claimed = controller.claim_next_job("worker")
    assert claimed is not None
    assert claimed.state == JobState.RUNNING
    assert claimed.worker_id == "worker"

    controller.record_event(claimed.id, "job.phase_changed", {"message": "Solving"})
    artifact = StoredArtifact("input.xlsx", "application/test", b"xlsx")
    completed = controller.complete_job(
        claimed.id,
        OptimizationResult(OptimizationOutcome.OPTIMAL, 42, "OPTIMAL", "optimality_proven"),
        artifact,
    )
    assert completed.state == JobState.COMPLETED
    assert completed.result is not None
    assert completed.result.outcome == OptimizationOutcome.OPTIMAL
    assert controller.get_artifact(completed.id, "input.xlsx") == artifact

    events = [event for event in controller.stream_events(completed.id, after_id=None, keepalive_seconds=0.01)]
    assert [event.type for event in events if event is not None] == [
        "job.state_changed",
        "job.state_changed",
        "job.phase_changed",
        "job.state_changed",
        "job.result_available",
    ]
    assert all(event.id is not None for event in events if event is not None)
    persisted_events = [event for event in events if event is not None]
    assert persisted_events[0].data["runtime"] == runtime_identity
    assert persisted_events[1].data["runtime"] == runtime_identity
    assert persisted_events[1].data["worker_id"] == "worker"


def test_store_reports_missing_input_and_artifacts(store):
    controller = _controller(store)
    created = _create(controller)

    with pytest.raises(JobArtifactNotFoundError):
        store.get_artifact(created.id, "input.xlsx")

    if isinstance(store, MemoryJobStore):
        store._records[created.id].input_bytes = None
    else:
        store._redis.delete(store._input_key(created.id))
    with pytest.raises(JobInputNotFoundError):
        controller.get_input(created.id)

    claimed = controller.claim_next_job("worker")
    assert claimed is not None
    artifact = StoredArtifact("input.xlsx", "application/test", b"xlsx")
    controller.complete_job(
        claimed.id,
        OptimizationResult(OptimizationOutcome.OPTIMAL, 42, "OPTIMAL", "optimality_proven"),
        artifact,
    )
    if isinstance(store, MemoryJobStore):
        store._records[created.id].artifacts.clear()
    else:
        store._redis.delete(store._artifact_key(created.id))
    with pytest.raises(JobArtifactNotFoundError):
        controller.get_artifact(created.id, artifact.name)


def test_store_handles_empty_queries_and_missing_jobs(store):
    now = datetime.now(timezone.utc)

    assert store.claim_next("worker", now, now + timedelta(seconds=30)) is None
    assert store.find_finished_before(now) == []
    assert store.find_claimed_before(now) == []
    store.check_health()

    with pytest.raises(JobNotFoundError):
        store.get("missing")
    with pytest.raises(JobNotFoundError):
        store.get_input("missing")
    with pytest.raises(JobNotFoundError):
        store.get_artifact("missing", "input.xlsx")
    with pytest.raises(JobNotFoundError):
        store.delete("missing", 1)


def test_store_rejects_duplicate_ids_and_prunes_terminal_jobs(store):
    controller = _controller(store, max_pending=2, max_retained=1)
    first = _create(controller, "first.yaml")
    limits = StoreLimits(max_pending=2, max_retained=1)

    with pytest.raises(StoreWriteConflictError):
        store.create(first, b"duplicate", limits, [])
    with pytest.raises(JobCapacityError, match="Too many jobs are retained"):
        _create(controller, "blocked.yaml")

    controller.cancel_job(first.id)
    replacement = _create(controller, "replacement.yaml")

    assert replacement.id != first.id
    with pytest.raises(JobNotFoundError):
        controller.get_job(first.id)


def test_store_rejects_stale_delete_and_missing_save(store):
    controller = _controller(store)
    created = _create(controller)

    with pytest.raises(StoreWriteConflictError):
        store.delete(created.id, created.revision + 1)
    store.delete(created.id, created.revision)
    with pytest.raises(JobNotFoundError):
        store.save(created, created.revision, [])


def test_store_reorders_queue_when_saved_without_events(store):
    now = datetime.now(timezone.utc)
    controller = _controller(store, now=now)
    first = _create(controller, "first.yaml")
    second = _create(controller, "second.yaml")

    cancelled = replace(first, state=JobState.CANCELLED, finished_at=now)
    saved = store.save(cancelled, first.revision, [])

    assert saved.state == JobState.CANCELLED
    events = store.stream_events(second.id, after_id=None, keepalive_seconds=0.01)
    assert [next(events).data["queue_position"], next(events).data["queue_position"]] == [2, 1]


def test_live_event_stream_emits_keepalive_after_catching_up(store):
    controller = _controller(store)
    created = _create(controller)
    events = store.stream_events(created.id, after_id=None, keepalive_seconds=0.01)
    initial = next(events)
    assert initial is not None

    resumed = store.stream_events(created.id, after_id=initial.id, keepalive_seconds=0.01)
    assert next(resumed) is None
    assert next(resumed) is None


def test_memory_event_stream_replays_from_invalid_cursor():
    store = MemoryJobStore()
    controller = _controller(store)
    created = _create(controller)

    event = next(store.stream_events(created.id, after_id="invalid", keepalive_seconds=0.01))

    assert event is not None
    assert event.type == "job.state_changed"


def test_redis_store_uses_artifact_metadata_defaults(fake_redis_store_factory):
    store = fake_redis_store_factory()
    controller = _controller(store)
    created = _create(controller)
    claimed = controller.claim_next_job("worker")
    assert claimed is not None
    artifact = StoredArtifact("input.xlsx", "application/test", b"xlsx")
    controller.complete_job(
        claimed.id,
        OptimizationResult(OptimizationOutcome.OPTIMAL, 42, "OPTIMAL", "optimality_proven"),
        artifact,
    )

    store._redis.delete(store._artifact_metadata_key(created.id))

    assert store.get_artifact(created.id, artifact.name) == StoredArtifact(
        "input.xlsx",
        "application/octet-stream",
        b"xlsx",
    )


def test_redis_store_removes_corrupt_queue_entries(fake_redis_store_factory):
    store = fake_redis_store_factory()
    now = datetime.now(timezone.utc)
    store._redis.zadd(store._queue_key, {"orphan": now.timestamp()})

    assert store.claim_next("worker", now, now + timedelta(seconds=30)) is None

    controller = _controller(store, now=now)
    created = _create(controller)
    controller.cancel_job(created.id)
    store._redis.zadd(store._queue_key, {created.id: now.timestamp()})

    assert store.claim_next("worker", now, now + timedelta(seconds=30)) is None


def test_redis_event_stream_treats_socket_timeout_as_keepalive(fake_redis_store_factory, monkeypatch):
    store = fake_redis_store_factory()
    controller = _controller(store)
    created = _create(controller)
    initial = next(store.stream_events(created.id, after_id=None, keepalive_seconds=0.01))
    assert initial is not None
    monkeypatch.setattr(store._stream_redis, "xread", Mock(side_effect=redis.exceptions.TimeoutError))

    resumed = store.stream_events(created.id, after_id=initial.id, keepalive_seconds=0.01)

    assert next(resumed) is None


@pytest.mark.parametrize("operation", ["create", "claim", "save", "delete"])
def test_redis_store_retries_watch_errors(fake_redis_store_factory, monkeypatch, operation):
    store = fake_redis_store_factory()
    controller = _controller(store)

    if operation == "create":
        _raise_watch_error_once(store, monkeypatch)
        assert _create(controller).state == JobState.QUEUED
        return

    created = _create(controller)
    if operation == "delete":
        created = controller.cancel_job(created.id)
    _raise_watch_error_once(store, monkeypatch)

    if operation == "claim":
        assert controller.claim_next_job("worker").state == JobState.RUNNING
    elif operation == "save":
        assert controller.cancel_job(created.id).state == JobState.CANCELLED
    else:
        controller.delete_job(created.id)
        with pytest.raises(JobNotFoundError):
            controller.get_job(created.id)


def test_store_rejects_events_from_stale_workers_and_terminal_jobs(store):
    controller = _controller(store)
    created = _create(controller)
    claimed = controller.claim_next_job("worker")
    assert claimed is not None

    accepted = controller.record_score_and_event(
        claimed.id,
        42,
        {"source": "accepted"},
        worker_id="worker",
    )
    stale = controller.record_event(
        claimed.id,
        "job.phase_changed",
        {"source": "stale"},
        worker_id="other-worker",
    )
    assert stale.revision == accepted.revision

    terminal = controller.fail_job(claimed.id, JobFailure("solver_failed", "failed"))
    late = controller.record_event(
        claimed.id,
        "job.phase_changed",
        {"source": "late"},
        worker_id="worker",
    )
    assert late.revision == terminal.revision

    events = [
        event
        for event in controller.stream_events(created.id, after_id=None, keepalive_seconds=0.01)
        if event is not None
    ]
    assert [(event.type, event.data.get("source")) for event in events] == [
        ("job.state_changed", None),
        ("job.state_changed", None),
        ("job.progressed", "accepted"),
        ("job.state_changed", None),
    ]


def test_store_queue_positions_are_derived_from_queue_order(store):
    controller = _controller(store)
    first = _create(controller, "first.yaml")
    second = _create(controller, "second.yaml")
    assert controller.get_job(first.id).queue_position == 1
    assert controller.get_job(second.id).queue_position == 2

    controller.claim_next_job("worker")
    assert controller.get_job(second.id).queue_position == 1


def test_store_caps_replayable_events_per_job(store_factory):
    controller = _controller(store_factory(max_events_per_job=4))
    created = _create(controller)
    for index in range(6):
        controller.record_event(created.id, "job.test", {"index": index})
    controller.cancel_job(created.id)

    events = [
        event
        for event in controller.stream_events(created.id, after_id=None, keepalive_seconds=0.01)
        if event is not None
    ]

    assert len(events) == 4
    assert [(event.type, event.data.get("index")) for event in events] == [
        ("job.test", 3),
        ("job.test", 4),
        ("job.test", 5),
        ("job.state_changed", None),
    ]


def test_controller_cancellation_policy_is_shared_by_stores(store):
    controller = _controller(store)
    queued = _create(controller)
    cancelled = controller.cancel_job(queued.id)
    assert cancelled.state == JobState.CANCELLED

    running = _create(controller, "running.yaml")
    controller.claim_next_job("worker")
    cancelling = controller.cancel_job(running.id)
    assert cancelling.state == JobState.CANCELLING
    stale = controller.complete_cancellation(running.id, "other-worker")
    assert stale.state == JobState.CANCELLING
    cancelled = controller.complete_cancellation(running.id, "worker")
    assert cancelled.state == JobState.CANCELLED
    assert cancelled.failure == JobFailure("cancelled", "Optimization cancelled.")


def test_store_enforces_atomic_pending_capacity(store):
    controller = _controller(store, max_pending=1, max_retained=1)
    _create(controller)
    with pytest.raises(JobCapacityError):
        _create(controller)


def test_store_enforces_capacity_across_concurrent_creates(store):
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=4, max_retained=4),
        retention_seconds=60,
        claim_lease_seconds=30,
    )

    def create(index: int):
        try:
            return controller.create_job(
                input_name=f"{index}.yaml",
                client_id="client",
                solver="ortools/cp-sat",
                prettify=False,
                timeout_seconds=60,
                input_bytes=b"apiVersion: alpha\n",
            )
        except JobCapacityError as error:
            return error

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(create, range(8)))

    assert sum(not isinstance(result, JobCapacityError) for result in results) == 4


def test_store_claims_each_job_at_most_once_under_concurrency(store):
    controller = _controller(store)
    created_ids = {_create(controller, f"{index}.yaml").id for index in range(6)}

    with ThreadPoolExecutor(max_workers=6) as executor:
        claimed = list(executor.map(lambda index: controller.claim_next_job(f"worker-{index}"), range(6)))

    claimed_ids = {job.id for job in claimed if job is not None}
    assert claimed_ids == created_ids
    assert len(claimed_ids) == len(claimed)


def test_revision_prevents_late_overwrite(store):
    controller = _controller(store)
    created = _create(controller)
    stale = controller.get_job(created.id)
    controller.cancel_job(created.id)

    with pytest.raises(StoreWriteConflictError):
        store.save(stale, stale.revision, [])


def test_controller_retries_internal_store_conflict_during_delete():
    class OneTimeDeleteConflictStore(MemoryJobStore):
        def __init__(self):
            super().__init__()
            self.conflict_pending = True

        def delete(self, job_id, expected_revision):
            if self.conflict_pending:
                self.conflict_pending = False
                raise StoreWriteConflictError("simulated write race")
            super().delete(job_id, expected_revision)

    store = OneTimeDeleteConflictStore()
    controller = _controller(store)
    created = _create(controller)
    controller.cancel_job(created.id)

    controller.delete_job(created.id)

    with pytest.raises(JobNotFoundError):
        controller.get_job(created.id)


def test_controller_backs_off_between_store_write_retries(monkeypatch):
    trace: list[str] = []
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        trace.append(f"operation-{attempts}")
        if attempts < 3:
            raise StoreWriteConflictError("simulated write race")
        return "saved"

    monkeypatch.setattr(
        "nurse_scheduling.server.retry.time.sleep",
        lambda seconds: trace.append(f"sleep-{seconds}"),
    )

    assert JobController._retry_store_write(operation) == "saved"
    assert trace == [
        "operation-1",
        "sleep-0.001",
        "operation-2",
        "sleep-0.002",
        "operation-3",
    ]


def test_retention_cleanup_removes_old_terminal_jobs(store):
    now = datetime.now(timezone.utc)
    controller = _controller(store, now=now)
    created = _create(controller)
    controller.cancel_job(created.id)

    later = JobController(
        store,
        limits=StoreLimits(max_pending=8, max_retained=32),
        retention_seconds=60,
        claim_lease_seconds=30,
        clock=lambda: now + timedelta(seconds=61),
    )
    assert later.expire_jobs() == [created.id]


def test_completed_job_can_resume_after_client_sleeps(store):
    now = datetime.now(timezone.utc)
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=8, max_retained=DEFAULT_MAX_RETAINED_JOBS),
        retention_seconds=DEFAULT_JOB_RETENTION_SECONDS,
        claim_lease_seconds=30,
        clock=lambda: now,
    )
    created = _create(controller)
    running = controller.claim_next_job("worker")
    assert running is not None

    event_stream = controller.stream_events(running.id, after_id=None, keepalive_seconds=0.01)
    while True:
        last_seen = next(event_stream)
        assert last_seen is not None
        if last_seen.type == "job.state_changed" and last_seen.data["state"] == "running":
            break

    artifact = StoredArtifact("input.xlsx", "application/test", b"xlsx")
    controller.complete_job(
        running.id,
        OptimizationResult(OptimizationOutcome.OPTIMAL, 42, "OPTIMAL", "optimality_proven"),
        artifact,
    )

    after_sleep = JobController(
        store,
        limits=StoreLimits(max_pending=8, max_retained=DEFAULT_MAX_RETAINED_JOBS),
        retention_seconds=DEFAULT_JOB_RETENTION_SECONDS,
        claim_lease_seconds=30,
        clock=lambda: now + timedelta(hours=23),
    )
    assert after_sleep.expire_jobs() == []

    replayed = list(
        after_sleep.stream_events(
            created.id,
            after_id=last_seen.id,
            keepalive_seconds=0.01,
        )
    )
    assert [event.type for event in replayed if event is not None] == [
        "job.state_changed",
        "job.result_available",
    ]
    assert after_sleep.get_artifact(created.id, artifact.name) == artifact


def test_terminal_event_stream_returns_immediately_when_cursor_is_caught_up(store):
    controller = _controller(store)
    created = _create(controller)
    controller.cancel_job(created.id)
    initial = [
        event
        for event in controller.stream_events(created.id, after_id=None, keepalive_seconds=0.01)
        if event is not None
    ]
    last_event_id = initial[-1].id
    assert last_event_id is not None

    started_at = time.monotonic()
    resumed = list(controller.stream_events(created.id, after_id=last_event_id, keepalive_seconds=1))

    assert resumed == []
    assert time.monotonic() - started_at < 0.5


def test_queue_position_events_track_queue_reordering(store):
    controller = _controller(store)
    first = _create(controller, "first.yaml")
    second = _create(controller, "second.yaml")

    controller.claim_next_job("worker")

    events = controller.stream_events(second.id, after_id=None, keepalive_seconds=0.01)
    queued = [next(events), next(events)]
    assert [event.data["queue_position"] for event in queued] == [2, 1]
    assert controller.get_job(first.id).state == JobState.RUNNING


def test_expired_worker_claim_fails_job_and_releases_capacity(store):
    now = datetime.now(timezone.utc)
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        claim_lease_seconds=10,
        clock=lambda: now,
        id_factory=lambda: "job_abandoned",
    )
    abandoned = _create(controller)
    controller.claim_next_job("lost-worker")

    recovery = JobController(
        store,
        limits=StoreLimits(max_pending=1, max_retained=2),
        retention_seconds=60,
        claim_lease_seconds=10,
        clock=lambda: now + timedelta(seconds=11),
        id_factory=lambda: "job_replacement",
    )
    assert recovery.renew_claim(abandoned.id, "lost-worker") is None
    assert recovery.is_stop_requested(abandoned.id, "lost-worker") is True
    assert recovery.expire_worker_claims() == [abandoned.id]
    failed = recovery.get_job(abandoned.id)
    assert failed.state == JobState.FAILED
    assert failed.failure == JobFailure(
        "worker_lost",
        "The optimization worker stopped before the job completed.",
    )
    assert _create(recovery).state == JobState.QUEUED
