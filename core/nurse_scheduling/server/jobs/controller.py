"""Application service owning optimization job lifecycle policy."""

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

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar
from uuid import uuid4

from ..errors import (
    JobArtifactNotReadyError,
    JobNotFoundError,
    JobOperationContentionError,
    JobOperationNotAllowedError,
    StoreWriteConflictError,
)
from ..job_store import JobStore
from .models import (
    Job,
    JobEvent,
    JobEventType,
    JobFailure,
    JobReplayError,
    JobReplayGap,
    JobRequest,
    JobState,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
    solver_supports_stop,
)


server_logger = logging.getLogger("nurse_scheduling.server")
Clock = Callable[[], datetime]
IdFactory = Callable[[], str]
Transition = Callable[[Job, datetime], tuple[Job, list[JobEvent], StoredArtifact | None]]
WriteResult = TypeVar("WriteResult")
STORE_WRITE_RETRY_INITIAL_DELAY_SECONDS = 0.001
STORE_WRITE_RETRY_MAX_DELAY_SECONDS = 0.05


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def new_job_id() -> str:
    """Return a high-entropy job identifier."""
    return f"job_{uuid4().hex}"


class JobController:
    """Coordinate all job use cases independently of HTTP and persistence."""

    def __init__(
        self,
        store: JobStore,
        *,
        limits: StoreLimits,
        retention_seconds: int,
        claim_lease_seconds: float,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_job_id,
    ):
        """Configure lifecycle policy around an injected job store."""
        self._store = store
        """Persistence contract used for all job data and atomic updates."""
        self._limits = limits
        """Pending and retained capacity enforced during job creation."""
        self._retention_seconds = retention_seconds
        """Age after which terminal job history is eligible for deletion."""
        self._claim_lease_seconds = claim_lease_seconds
        """Duration assigned to each new or renewed worker claim."""
        self._clock = clock
        """Clock used for lifecycle timestamps and deterministic tests."""
        self._id_factory = id_factory
        """Factory used to allocate externally visible job IDs."""

    def create_job(
        self,
        *,
        input_name: str,
        client_id: str,
        solver: str,
        prettify: bool | None,
        timeout_seconds: int,
        input_bytes: bytes,
    ) -> Job:
        """Create and enqueue a job with its submitted input.

        ID collisions are retried before reporting an application conflict.

        Raises:
            JobCapacityError: If pending or retained capacity is exhausted.
            JobOperationContentionError: If a unique job ID cannot be allocated.
        """
        now = self._clock()

        def create() -> Job:
            """Build and atomically persist one job-ID candidate."""
            job = Job(
                id=self._id_factory(),
                state=JobState.QUEUED,
                request=JobRequest(
                    input_name=input_name,
                    client_id=client_id,
                    solver=solver,
                    prettify=prettify,
                    timeout_seconds=timeout_seconds,
                ),
                created_at=now,
            )
            return self._store.create(job, input_bytes, self._limits, [self._state_event(job, now)])

        created = self._retry_store_write(
            create,
            failure_message="Unable to allocate a unique job identifier",
        )
        server_logger.info(
            "[server:job] queued job_id=%s solver=%s timeout=%s input_name=%s queue_position=%s client_id=%s",
            created.id,
            created.request.solver,
            created.request.timeout_seconds,
            created.request.input_name,
            created.queue_position,
            created.request.client_id,
        )
        return created

    def get_job(self, job_id: str) -> Job:
        """Return the current job snapshot.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        return self._store.get(job_id)

    def get_input(self, job_id: str) -> bytes:
        """Return the original input submitted for a job.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobInputNotFoundError: If the submitted input is unavailable.
        """
        return self._store.get_input(job_id)

    def get_artifact(self, job_id: str, name: str) -> StoredArtifact:
        """Return a completed job's named artifact.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobArtifactNotReadyError: If the job has not produced an artifact.
            JobArtifactNotFoundError: If the named artifact does not exist.
        """
        job = self.get_job(job_id)
        if job.artifact_name is None:
            if job.state.terminal:
                raise JobArtifactNotReadyError("No schedule artifact is available for this job")
            raise JobArtifactNotReadyError("The schedule artifact is not ready")
        return self._store.get_artifact(job_id, name)

    def claim_next_job(self, worker_id: str) -> Job | None:
        """Claim the next queued job and assign it a worker lease.

        Return the claimed running job, or `None` when the queue is empty.
        """
        now = self._clock()
        job = self._store.claim_next(
            worker_id,
            now,
            now + timedelta(seconds=self._claim_lease_seconds),
        )
        if job is not None:
            server_logger.info(
                "[server:job] started job_id=%s solver=%s queue_wait_seconds=%.3f client_id=%s",
                job.id,
                job.request.solver,
                ((job.started_at or self._clock()) - job.created_at).total_seconds(),
                job.request.client_id,
            )
        return job

    def record_event(
        self,
        job_id: str,
        event_type: str,
        data: dict[str, Any],
        *,
        worker_id: str | None = None,
    ) -> Job:
        """Persist progress or phase data without changing lifecycle state.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """

        def transition(job: Job, now: datetime) -> tuple[Job, list[JobEvent], StoredArtifact | None]:
            """Append an event only while the reporting worker owns an active job."""
            if job.state.terminal or (worker_id is not None and job.worker_id != worker_id):
                return job, [], None
            return job, [JobEvent(type=event_type, data=data, occurred_at=now)], None

        return self._update_job_with_retry(job_id, transition)

    def renew_claim(self, job_id: str, worker_id: str) -> Job | None:
        """Extend a live worker claim without emitting a client event.

        Return the renewed job, or `None` when the claim is inactive, expired,
        or owned by another worker. An expired lease cannot be resurrected.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """

        did_renew = False

        def transition(job: Job, now: datetime):
            """Return a renewed job only while this worker owns the claim."""
            nonlocal did_renew
            did_renew = False
            if (
                job.state not in {JobState.RUNNING, JobState.CANCELLING}
                or job.worker_id != worker_id
                or job.claim_expires_at is None
                or job.claim_expires_at <= now
            ):
                return job, [], None
            did_renew = True
            renewed = replace(job, claim_expires_at=now + timedelta(seconds=self._claim_lease_seconds))
            return renewed, [], None

        renewed = self._update_job_with_retry(job_id, transition)
        return renewed if did_renew else None

    def record_score_and_event(
        self,
        job_id: str,
        score: int,
        data: dict[str, Any],
        *,
        worker_id: str | None = None,
    ) -> Job:
        """Persist the latest score as progress without manufacturing a result.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """
        payload = dict(data)
        payload["score"] = score
        return self.record_event(job_id, JobEventType.PROGRESSED, payload, worker_id=worker_id)

    def complete_job(
        self,
        job_id: str,
        result: OptimizationResult,
        artifact: StoredArtifact | None,
    ) -> Job:
        """Complete a job unless a cancellation request takes precedence.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """

        def transition(job: Job, now: datetime):
            """Build the terminal completion or cancellation transition."""
            if job.state.terminal:
                return job, [], None
            if job.cancel_requested:
                cancelled = replace(
                    job,
                    state=JobState.CANCELLED,
                    finished_at=now,
                    failure=JobFailure(code="cancelled", message="Optimization cancelled."),
                    queue_position=None,
                    claim_expires_at=None,
                )
                return cancelled, [self._state_event(cancelled, now)], None
            completed = replace(
                job,
                state=JobState.COMPLETED,
                result=result,
                failure=None,
                finished_at=now,
                artifact_name=artifact.name if artifact is not None else None,
                queue_position=None,
                claim_expires_at=None,
            )
            return completed, [self._state_event(completed, now), self._result_event(completed, now)], artifact

        completed = self._update_job_with_retry(job_id, transition)
        self._log_terminal_job(completed)
        return completed

    def fail_job(self, job_id: str, failure: JobFailure) -> Job:
        """Fail a job unless a cancellation request takes precedence.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """

        def transition(job: Job, now: datetime):
            """Build the terminal failure or cancellation transition."""
            if job.state.terminal:
                return job, [], None
            if job.cancel_requested:
                failed = replace(
                    job,
                    state=JobState.CANCELLED,
                    failure=JobFailure(code="cancelled", message="Optimization cancelled."),
                    finished_at=now,
                    queue_position=None,
                    claim_expires_at=None,
                )
            else:
                failed = replace(
                    job,
                    state=JobState.FAILED,
                    failure=failure,
                    finished_at=now,
                    queue_position=None,
                    claim_expires_at=None,
                )
            return failed, [self._state_event(failed, now)], None

        failed = self._update_job_with_retry(job_id, transition)
        self._log_terminal_job(failed)
        return failed

    def cancel_job(self, job_id: str) -> Job:
        """Cancel a queued job or request cooperative cancellation of a running job.

        Repeated cancellation and terminal jobs are returned unchanged.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationNotAllowedError: If the solver does not support cancellation.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """

        def transition(job: Job, now: datetime):
            """Build an immediate or cooperative cancellation transition."""
            if job.state.terminal or job.cancel_requested:
                return job, [], None
            if job.state == JobState.QUEUED:
                cancelled = replace(
                    job,
                    state=JobState.CANCELLED,
                    cancel_requested=True,
                    failure=JobFailure(code="cancelled", message="Optimization cancelled."),
                    finished_at=now,
                    queue_position=None,
                )
                return cancelled, [self._state_event(cancelled, now)], None
            if not solver_supports_stop(job.request.solver):
                raise JobOperationNotAllowedError("This solver does not support cancellation")
            cancelling = replace(job, state=JobState.CANCELLING, cancel_requested=True)
            return cancelling, [self._state_event(cancelling, now)], None

        job = self._update_job_with_retry(job_id, transition)
        server_logger.info(
            "[server:job] cancel-requested job_id=%s state=%s client_id=%s",
            job.id,
            job.state.value,
            job.request.client_id,
        )
        return job

    def request_early_completion(self, job_id: str) -> Job:
        """Ask a supported running solver to return its current result.

        Repeated requests and terminal jobs are returned unchanged.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationNotAllowedError: If the state or solver does not support this control.
            JobOperationContentionError: If concurrent updates exhaust the retry limit.
        """

        def transition(job: Job, now: datetime):
            """Build the early-completion control transition."""
            if job.state.terminal or job.early_completion_requested:
                return job, [], None
            if job.state != JobState.RUNNING:
                raise JobOperationNotAllowedError("Early completion is only available while a job is running")
            if not solver_supports_stop(job.request.solver):
                raise JobOperationNotAllowedError("This solver does not support early completion")
            updated = replace(job, early_completion_requested=True)
            event = JobEvent(
                type=JobEventType.CONTROL_CHANGED,
                data={"early_completion_requested": True},
                occurred_at=now,
            )
            return updated, [event], None

        return self._update_job_with_retry(job_id, transition)

    def is_stop_requested(self, job_id: str, worker_id: str | None = None) -> bool:
        """Return whether a worker should stop executing a job.

        Terminal state and lost claim ownership stop stale workers after lease
        expiry, in addition to explicit cancellation and early completion.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        job = self.get_job(job_id)
        lost_claim = worker_id is not None and job.worker_id != worker_id
        expired_claim = worker_id is not None and (
            job.claim_expires_at is None or job.claim_expires_at <= self._clock()
        )
        return (
            job.state.terminal or lost_claim or expired_claim or job.cancel_requested or job.early_completion_requested
        )

    def stream_events(
        self,
        job_id: str,
        *,
        after_id: str | None,
        keepalive_seconds: float,
    ) -> Iterator[JobEvent | JobReplayError | JobReplayGap | None]:
        """Stream persisted events after a cursor until the job becomes terminal.

        Iteration blocks up to the keepalive interval when no newer event exists.

        Raises:
            JobNotFoundError: If the job does not exist or is deleted while streaming.
        """
        return self._store.stream_events(job_id, after_id, keepalive_seconds)

    def delete_job(self, job_id: str) -> None:
        """Delete a terminal job and all associated data.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationNotAllowedError: If the job is not terminal.
            JobOperationContentionError: If concurrent writes exhaust the retry limit.
        """

        def delete() -> Job:
            """Validate and atomically delete the current job revision."""
            job = self.get_job(job_id)
            if not job.state.terminal:
                raise JobOperationNotAllowedError("Only a terminal job can be deleted")
            self._store.delete(job.id, job.revision)
            return job

        deleted = self._retry_store_write(delete)
        server_logger.info(
            "[server:job] deleted job_id=%s state=%s client_id=%s",
            deleted.id,
            deleted.state.value,
            deleted.request.client_id,
        )

    def expire_jobs(self) -> list[str]:
        """Delete terminal jobs older than the configured retention period.

        Return the IDs successfully deleted during this maintenance pass.
        """
        cutoff = self._clock() - timedelta(seconds=self._retention_seconds)
        expired_ids: list[str] = []
        for job in self._store.find_finished_before(cutoff):
            try:
                self._store.delete(job.id, job.revision)
            except (StoreWriteConflictError, JobNotFoundError):
                # Maintenance uses a stale snapshot safely; a later pass re-evaluates it.
                continue
            expired_ids.append(job.id)
            server_logger.info(
                "[server:job] expired job_id=%s state=%s reason=retention client_id=%s",
                job.id,
                job.state.value,
                job.request.client_id,
            )
        return expired_ids

    def expire_worker_claims(self) -> list[str]:
        """Terminate jobs whose worker stopped renewing its execution claim.

        Return the IDs successfully transitioned during this maintenance pass.
        """
        now = self._clock()
        expired_ids: list[str] = []
        for candidate in self._store.find_claimed_before(now):
            did_expire = False

            def transition(job: Job, transition_time: datetime):
                """Terminate the job only if its claim remains expired."""
                nonlocal did_expire
                did_expire = False
                if (
                    job.state not in {JobState.RUNNING, JobState.CANCELLING}
                    or job.claim_expires_at is None
                    or job.claim_expires_at > transition_time
                ):
                    return job, [], None
                if job.cancel_requested:
                    failed = replace(
                        job,
                        state=JobState.CANCELLED,
                        failure=JobFailure(code="cancelled", message="Optimization cancelled."),
                        finished_at=transition_time,
                        queue_position=None,
                        claim_expires_at=None,
                    )
                else:
                    failed = replace(
                        job,
                        state=JobState.FAILED,
                        failure=JobFailure(
                            code="worker_lost",
                            message="The optimization worker stopped before the job completed.",
                        ),
                        finished_at=transition_time,
                        queue_position=None,
                        claim_expires_at=None,
                    )
                did_expire = True
                return failed, [self._state_event(failed, transition_time)], None

            expired = self._update_job_with_retry(candidate.id, transition)
            if did_expire:
                expired_ids.append(expired.id)
                self._log_terminal_job(expired)
        return expired_ids

    def _update_job_with_retry(self, job_id: str, transition: Transition, max_attempts: int = 20) -> Job:
        """Compute and persist a job update, retrying optimistic write conflicts.

        Raises:
            JobNotFoundError: If the job does not exist.
            JobOperationContentionError: If conflicts exhaust `max_attempts`.
        """

        def update() -> Job:
            """Recompute and persist the transition from the latest job revision."""
            current = self._store.get(job_id)
            replacement, events, artifact = transition(current, self._clock())
            if replacement is current and not events and artifact is None:
                return current
            return self._store.save(replacement, current.revision, events, artifact)

        return self._retry_store_write(update, max_attempts=max_attempts)

    @staticmethod
    def _retry_store_write(
        operation: Callable[[], WriteResult],
        *,
        max_attempts: int = 20,
        failure_message: str = "Job changed too frequently; retry the request",
    ) -> WriteResult:
        """Retry a complete store write after internal atomic-write conflicts.

        Re-running the complete operation lets callers regenerate IDs or re-read
        current revisions before each write attempt.

        Raises:
            JobOperationContentionError: If conflicts exhaust `max_attempts`.
        """
        for attempt in range(max_attempts):
            if attempt > 0:
                delay_seconds = min(
                    STORE_WRITE_RETRY_INITIAL_DELAY_SECONDS * (2 ** (attempt - 1)),
                    STORE_WRITE_RETRY_MAX_DELAY_SECONDS,
                )
                time.sleep(delay_seconds)
            try:
                return operation()
            except StoreWriteConflictError:
                # Retry the whole callback so it can regenerate IDs or re-read revisions.
                continue
        raise JobOperationContentionError(failure_message)

    @staticmethod
    def _state_event(job: Job, occurred_at: datetime) -> JobEvent:
        """Build a lifecycle event from the current job state."""
        data: dict[str, Any] = {
            "state": job.state.value,
            "queue_position": job.queue_position,
            "cancel_requested": job.cancel_requested,
            "early_completion_requested": job.early_completion_requested,
        }
        if job.failure is not None:
            data["error"] = {"code": job.failure.code, "message": job.failure.message}
        return JobEvent(type=JobEventType.STATE_CHANGED, data=data, occurred_at=occurred_at)

    @staticmethod
    def _result_event(job: Job, occurred_at: datetime) -> JobEvent:
        """Build a result-available event for a completed job.

        Raises:
            AssertionError: If the job has no optimization result.
        """
        assert job.result is not None
        return JobEvent(
            type=JobEventType.RESULT_AVAILABLE,
            data={
                "outcome": job.result.outcome.value,
                "score": job.result.score,
                "solver_status": job.result.solver_status,
                "termination_reason": job.result.termination_reason,
                "artifact_name": job.artifact_name,
            },
            occurred_at=occurred_at,
        )

    @staticmethod
    def _log_terminal_job(job: Job) -> None:
        """Log completion metrics when the supplied job is terminal."""
        if not job.state.terminal:
            return
        finished_at = job.finished_at or utc_now()
        started_at = job.started_at or job.created_at
        server_logger.info(
            "[server:job] completed job_id=%s state=%s outcome=%s score=%s duration_seconds=%.3f client_id=%s",
            job.id,
            job.state.value,
            job.result.outcome.value if job.result is not None else None,
            job.result.score if job.result is not None else None,
            (finished_at - started_at).total_seconds(),
            job.request.client_id,
        )
