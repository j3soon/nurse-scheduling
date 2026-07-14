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
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from nurse_scheduling.server.errors import JobCapacityError, JobNotFoundError, StoreWriteConflictError
from nurse_scheduling.server.config import DEFAULT_JOB_RETENTION_SECONDS, DEFAULT_MAX_RETAINED_JOBS
from nurse_scheduling.server.jobs.controller import JobController, utc_now
from nurse_scheduling.server.jobs.models import (
    JobFailure,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
)
from nurse_scheduling.server.stores.memory import MemoryJobStore


def _redis_url() -> str | None:
    return os.getenv("JOB_REDIS_TEST_URL") or os.getenv("JOB_REDIS_URL")


def _delete_redis_prefix(url: str, prefix: str) -> None:
    redis = pytest.importorskip("redis")
    client = redis.Redis.from_url(url)
    keys = list(client.scan_iter(f"{prefix}:*"))
    if keys:
        client.delete(*keys)


@pytest.fixture(params=["memory", "redis"])
def store(request):
    if request.param == "memory":
        yield MemoryJobStore()
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

    prefix = f"nurse_scheduling:test:jobs:{uuid.uuid4().hex}"
    _delete_redis_prefix(url, prefix)
    instance = RedisJobStore(url=url, key_prefix=prefix)
    try:
        yield instance
    finally:
        _delete_redis_prefix(url, prefix)


def _controller(store, *, max_pending=8, max_retained=32, now=None):
    clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    sequence = iter(f"job_{index}" for index in range(100))
    return JobController(
        store,
        limits=StoreLimits(max_pending=max_pending, max_retained=max_retained),
        retention_seconds=60,
        claim_lease_seconds=30,
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


def test_utc_now_returns_timezone_aware_utc_datetime():
    assert utc_now().tzinfo is timezone.utc


def test_store_round_trips_lifecycle_input_events_and_artifact(store):
    controller = _controller(store)
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


def test_store_queue_positions_are_derived_from_queue_order(store):
    controller = _controller(store)
    first = _create(controller, "first.yaml")
    second = _create(controller, "second.yaml")
    assert controller.get_job(first.id).queue_position == 1
    assert controller.get_job(second.id).queue_position == 2

    controller.claim_next_job("worker")
    assert controller.get_job(second.id).queue_position == 1


def test_controller_cancellation_policy_is_shared_by_stores(store):
    controller = _controller(store)
    queued = _create(controller)
    cancelled = controller.cancel_job(queued.id)
    assert cancelled.state == JobState.CANCELLED

    running = _create(controller, "running.yaml")
    controller.claim_next_job("worker")
    cancelling = controller.cancel_job(running.id)
    assert cancelling.state == JobState.CANCELLING
    failed = controller.fail_job(running.id, JobFailure("solver_failed", "ignored after cancellation"))
    assert failed.state == JobState.CANCELLED


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
    assert recovery.expire_worker_claims() == [abandoned.id]
    failed = recovery.get_job(abandoned.id)
    assert failed.state == JobState.FAILED
    assert failed.failure == JobFailure(
        "worker_lost",
        "The optimization worker stopped before the job completed.",
    )
    assert _create(recovery).state == JobState.QUEUED
