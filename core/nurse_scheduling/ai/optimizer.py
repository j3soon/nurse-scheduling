"""Background optimization support for AI chat sessions."""

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

# This code is mostly AI generated.

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .config import MAX_OPTIMIZER_RESULT_BYTES, MAX_OPTIMIZER_RUNS_PER_SESSION, MAX_SCHEDULE_BYTES
from .optimizer_privacy import OptimizerResultError, prepare_optimizer_schedule, restore_people_ids
from .result_context import build_request_audit, build_result_context

OPTIMIZER_TOOL = "optimizer"
WORKSPACE_OPTIMIZER_RESULT = "/workspace/optimizer-results/optimized-schedule.xlsx"
TERMINAL_STATES = frozenset({"completed", "cancelled", "failed"})
MAX_REJECTION_DETAIL_CHARS = 300
logger = logging.getLogger("nurse_scheduling.ai.optimizer")


def optimizer_completion_message(result_data: dict[str, Any]) -> str:
    """Render the completion turn shared by production and controlled evaluations."""
    if (result_data.get("result") or {}).get("score") is not None:
        result_data = {
            **result_data,
            "score_direction": "maximize",
            "score_comparison_scope": "Compare only scores from unchanged constraints and weights.",
        }
    result_path = WORKSPACE_OPTIMIZER_RESULT if result_data["download_available"] else "unavailable"
    download_status = (
        "The user can already download this workbook with the chat's Download result button.\n"
        if result_data["download_available"]
        else ""
    )
    return (
        f"Optimizer job finished. Result workbook: {result_path}.\n"
        f"{download_status}"
        f"Optimizer result JSON:\n{json.dumps(result_data, ensure_ascii=False)}"
    )


class OptimizerError(Exception):
    """The configured optimizer transport or response failed."""


class OptimizerResultUnavailable(Exception):
    """A session-owned optimizer result is not available for download."""


class OptimizerJobUnavailable(Exception):
    """The requested optimizer job does not belong to this session."""


class OptimizerJobPayload(BaseModel):
    """Subset of the optimizer job response used by the assistant."""

    id: str
    state: str
    terminal: bool = False
    queue_position: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    backend: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    controls: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict)


class OptimizerBackend(Protocol):
    """Transport boundary used by session-scoped optimization jobs."""

    async def submit(
        self, schedule_yaml: str, timeout_seconds: int | None, client_address: str | None = None
    ) -> OptimizerJobPayload: ...

    async def get(self, job_id: str) -> OptimizerJobPayload: ...

    def progress_events(self, job_id: str, client_address: str | None = None) -> AsyncIterator[dict[str, Any]]: ...

    async def finish_now(self, job_id: str) -> OptimizerJobPayload: ...

    async def cancel(self, job_id: str) -> OptimizerJobPayload: ...

    async def result_artifact(self, job: OptimizerJobPayload) -> "OptimizerArtifact": ...

    async def delete(self, job_id: str) -> None: ...

    async def close(self) -> None: ...


@dataclass
class SessionOptimization:
    """One optimizer job whose remote identifier remains server-side."""

    id: str
    session_id: str
    remote_id: str
    source_sha256: str
    payload: OptimizerJobPayload
    original_id_by_anonymized_id: dict[str, str]
    people_count: int
    schedule_yaml: str
    submitted_yaml: str = ""
    model_selection: dict[str, str] | None = None
    backend: dict[str, Any] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)
    client_address: str | None = None
    """Browser address that the optimizer bounds this job's submission and event streams by."""
    artifact: "OptimizerArtifact | None" = None
    artifact_saved: bool = False
    retired: asyncio.Event = field(default_factory=asyncio.Event)
    deleted: bool = False
    finish_now_requested_by: Literal["user", "agent"] | None = None
    finish_now_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def completion_details(self) -> dict[str, Any]:
        """Keep timing and early-completion attribution in events, reviews, and archives."""
        payload = self.payload
        elapsed = (
            max(0, (payload.finished_at - payload.started_at).total_seconds())
            if payload.started_at is not None and payload.finished_at is not None
            else None
        )
        return {
            "created_at": payload.created_at.isoformat() if payload.created_at else None,
            "started_at": payload.started_at.isoformat() if payload.started_at else None,
            "finished_at": payload.finished_at.isoformat() if payload.finished_at else None,
            "elapsed_seconds": elapsed,
            "finish_now_requested_by": self.finish_now_requested_by,
        }

    def observe(self, payload: OptimizerJobPayload) -> None:
        """Terminal snapshots dominate late control and poll responses."""
        if not _is_terminal(self.payload):
            self.payload = payload


@dataclass(frozen=True)
class OptimizerArtifact:
    """A completed workbook retained for an authenticated browser download."""

    content: bytes
    filename: str
    media_type: str
    schedule_context: bytes | None = None

    @property
    def retained_bytes(self) -> int:
        """Include compiled selectors in the result cache budget."""
        return len(self.content) + len(self.schedule_context or b"")


CompletionCallback = Callable[[str, str, OptimizerArtifact | None, dict[str, str] | None], Awaitable[None]]
UpdateCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class OptimizerSession:
    """One revocable owner for run limits, submission and the latest job."""

    runs: int = 0
    reservation: object | None = None
    latest: str | None = None


class SessionOptimizer:
    """Launch, monitor, and control one background optimization per chat session."""

    def __init__(
        self,
        backend: OptimizerBackend,
        *,
        poll_interval_seconds: float,
        on_completion: CompletionCallback,
        on_update: UpdateCallback | None = None,
        default_timeout_seconds: int = 300,
        status_failure_grace_seconds: float = 60.0,
        max_sessions: int = 1000,
        max_runs_per_session: int = MAX_OPTIMIZER_RUNS_PER_SESSION,
        max_result_bytes: int = MAX_OPTIMIZER_RESULT_BYTES,
        max_cached_result_bytes: int = 100_000_000,
        max_schedule_bytes: int = MAX_SCHEDULE_BYTES,
        save_result: Callable[[SessionOptimization, OptimizerArtifact | None], Awaitable[str | None]] | None = None,
        load_artifact: Callable[[str, str | None], Awaitable[OptimizerArtifact | None]] | None = None,
    ) -> None:
        self._backend = backend
        self._poll_interval_seconds = poll_interval_seconds
        self._on_completion = on_completion
        self._on_update = on_update
        self._default_timeout_seconds = default_timeout_seconds
        self._status_failure_grace_seconds = status_failure_grace_seconds
        self._max_sessions = max_sessions
        self._max_runs_per_session = max_runs_per_session
        self._max_result_bytes = max_result_bytes
        self._max_cached_result_bytes = max_cached_result_bytes
        self._max_schedule_bytes = max_schedule_bytes
        self._save_result = save_result
        self._load_artifact = load_artifact
        self._jobs: dict[str, SessionOptimization] = {}
        self._sessions: dict[str, OptimizerSession] = {}
        self._artifact_order: list[str] = []
        self._cached_artifact_bytes = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._submissions: set[asyncio.Task] = set()
        self._closed = False

    async def close(self) -> None:
        self._closed = True
        for session_id in tuple(self._sessions):
            self.forget_session(session_id)
        # Keep ownership of in-flight submissions until the bounded transport returns.
        await asyncio.gather(*tuple(self._submissions), return_exceptions=True)
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._backend.close()

    async def result_artifact(self, session_id: str, job_id: str) -> OptimizerArtifact:
        """Return a completed artifact only to the session that started it."""
        if self._load_artifact is not None and (artifact := await self._load_artifact(session_id, job_id)):
            return artifact
        job = self._jobs.get(job_id)
        if job is None or job.session_id != session_id:
            raise OptimizerResultUnavailable("Optimizer result not found.")
        if job.artifact is None:
            raise OptimizerResultUnavailable("This optimizer run has no downloadable result.")
        return job.artifact

    async def latest_result_artifact(self, session_id: str) -> OptimizerArtifact | None:
        """Return the newest finished workbook for a follow-up sandbox turn."""
        try:
            for job in reversed(self._jobs.values()):
                # A run that is still going has no result yet, so an older workbook
                # remains current. A finished run without one makes every earlier
                # workbook stale, and mounting it would misreport the latest result.
                if job.session_id != session_id or not _is_terminal(job.payload):
                    continue
                # A later recovery write can persist a result whose initial save failed.
                if self._load_artifact is not None:
                    return await self._load_artifact(session_id, job.id)
                return job.artifact
            return None if self._load_artifact is None else await self._load_artifact(session_id, None)
        except HTTPException:
            # Workbook inspection is optional. Explicit downloads still report storage errors.
            logger.warning("Optimizer workbook could not be loaded for chat session_id=%s", session_id)
            return None

    def has_unfinished_run(self, session_id: str) -> bool:
        """Report whether retiring the session would cancel one of its runs."""
        owner = self._sessions.get(session_id)
        return (owner is not None and owner.reservation is not None) or any(
            job.session_id == session_id and not _is_terminal(job.payload) for job in self._jobs.values()
        )

    def forget_session(self, session_id: str) -> None:
        """Revoke the owner synchronously. Its jobs perform their own remote cleanup."""
        for job in self._jobs.values():
            if job.session_id == session_id:
                job.retired.set()
        self._discard_session(session_id)

    async def start(
        self,
        session_id: str,
        schedule_yaml: str,
        timeout_seconds: int | None,
        client_address: str | None = None,
        model_selection: dict[str, str] | None = None,
    ) -> SessionOptimization:
        """Submit one optimizer job for a session, attributed to the browser address that asked for it."""
        if self._closed:
            raise OptimizerError("The optimizer service is shutting down.")
        owner = self._sessions.get(session_id)
        if owner is None:
            if len(self._sessions) >= self._max_sessions:
                raise OptimizerError("The optimizer session limit has been reached.")
            owner = OptimizerSession()
            self._sessions[session_id] = owner
        if owner.reservation is not None:
            raise OptimizerError("An optimizer run for this chat session is already being submitted.")
        if owner.runs >= self._max_runs_per_session:
            raise OptimizerError(
                f"This chat session has reached its limit of {self._max_runs_per_session} optimizer runs."
            )
        current = self._latest(session_id)
        if current is not None and not _is_terminal(current.payload):
            raise OptimizerError(
                f"Optimizer job {current.id} is already {current.payload.state}. Check it or finish it now."
            )
        # Reserve before the first await, including threaded validation.
        reservation = object()
        owner.reservation = reservation
        owner.runs += 1
        submission = asyncio.create_task(
            self._submit(
                session_id, owner, reservation, schedule_yaml, timeout_seconds, client_address, model_selection
            )
        )
        self._submissions.add(submission)

        def submitted(task: asyncio.Task) -> None:
            self._submissions.discard(task)
            if not task.cancelled():
                task.exception()

        submission.add_done_callback(submitted)
        try:
            # Keep ownership without reporting a late rejection after caller cancellation.
            await asyncio.wait((submission,))
            return submission.result()
        except asyncio.CancelledError:
            self._release_reservation(session_id, owner, reservation)
            # The owned submission disposes of any late response after revocation.
            raise

    async def _submit(
        self,
        session_id: str,
        owner: OptimizerSession,
        reservation: object,
        schedule_yaml: str,
        timeout_seconds: int | None,
        client_address: str | None,
        model_selection: dict[str, str] | None,
    ) -> SessionOptimization:
        def owns_submission() -> bool:
            return not self._closed and self._sessions.get(session_id) is owner and owner.reservation is reservation

        expired = OptimizerError("This chat session expired while the optimizer job was starting.")
        try:
            prepared = await asyncio.to_thread(prepare_optimizer_schedule, schedule_yaml, self._max_schedule_bytes)
            if not owns_submission():
                raise expired
            payload = await self._backend.submit(
                prepared.submission_yaml,
                self._default_timeout_seconds if timeout_seconds is None else timeout_seconds,
                client_address=client_address,
            )
        except ValueError as exc:
            self._release_reservation(session_id, owner, reservation)
            raise OptimizerError(f"The optimizer requires a valid frontend schedule. {exc}")
        except OptimizerError as exc:
            logger.warning("Optimizer submission failed: %s", exc)
            self._release_reservation(session_id, owner, reservation)
            raise OptimizerError(f"The optimizer could not accept the schedule. {exc}")
        except BaseException:
            self._release_reservation(session_id, owner, reservation)
            raise
        retired = not owns_submission()
        if not retired:
            owner.reservation = None
        job = SessionOptimization(
            id=f"opt_{uuid4().hex}",
            session_id=session_id,
            remote_id=payload.id,
            source_sha256=hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest(),
            payload=payload,
            original_id_by_anonymized_id=prepared.original_id_by_anonymized_id,
            people_count=prepared.people_count,
            schedule_yaml=schedule_yaml,
            submitted_yaml=prepared.submission_yaml,
            model_selection=model_selection,
            backend=payload.backend or {},
            request={
                **payload.request,
                "timeout_seconds": payload.request.get(
                    "timeout_seconds", self._default_timeout_seconds if timeout_seconds is None else timeout_seconds
                ),
            },
            client_address=client_address,
        )
        if retired:
            job.retired.set()
        else:
            self._jobs[job.id] = job
            owner.latest = job.id
        self._start_task(self._run_job(job))
        if retired:
            raise expired
        if not _is_terminal(job.payload):
            await self._notify_update(job)
        return job

    async def _run_job(self, job: SessionOptimization) -> None:
        """Own progress, monitoring, result delivery and remote cleanup as one scope."""
        progress = asyncio.create_task(self._relay_progress(job))
        try:
            await self._monitor(job)
            if not progress.done():
                try:
                    await asyncio.wait_for(asyncio.shield(progress), timeout=1)
                except TimeoutError:
                    progress.cancel()
            await asyncio.gather(progress, return_exceptions=True)
            if not _is_terminal(job.payload):
                return
            if self._jobs.get(job.id) is job:
                await self._complete(job)
            else:
                await self._delete_retired(job)
        except asyncio.CancelledError:
            # Shutdown also owns the remote side of a still-running job.
            if not _is_terminal(job.payload):
                await self._cancel_retired(job)
            if _is_terminal(job.payload):
                await self._delete_retired(job)
            raise
        finally:
            progress.cancel()
            await asyncio.gather(progress, return_exceptions=True)
            if _is_terminal(job.payload):
                await self._delete_retired(job)

    def status(self, session_id: str) -> SessionOptimization:
        job = self._latest(session_id)
        if job is None:
            raise OptimizerError("No optimizer job has been started in this chat session.")
        return job

    async def _cancel_retired(self, job: SessionOptimization) -> None:
        try:
            payload = await self._backend.cancel(job.remote_id)
        except OptimizerError as exc:
            logger.warning("Optimizer cancellation failed job_id=%s error=%s", job.id, exc)
            return
        job.observe(payload)

    async def _delete_retired(self, job: SessionOptimization) -> None:
        if job.deleted:
            return
        try:
            await self._backend.delete(job.remote_id)
        except OptimizerError as exc:
            logger.warning("Optimizer cleanup failed job_id=%s error=%s", job.id, exc)
        job.deleted = True

    async def finish_now(
        self, session_id: str, job_id: str | None = None, *, requested_by: Literal["user", "agent"] = "agent"
    ) -> tuple[SessionOptimization, bool]:
        job = self._jobs.get(job_id) if job_id is not None else self._latest(session_id)
        if job_id is not None and (job is None or job.session_id != session_id):
            raise OptimizerJobUnavailable("Optimizer job not found.")
        if job is None:
            raise OptimizerError("No optimizer job has been started in this chat session.")
        async with job.finish_now_lock:
            if _is_terminal(job.payload) or job.finish_now_requested_by is not None:
                return job, False
            # Completion can arrive before the control response. Record intent before
            # awaiting it so the review retains the trigger and the solver's actual reason.
            job.finish_now_requested_by = requested_by
            try:
                payload = await self._backend.finish_now(job.remote_id)
            except asyncio.CancelledError:
                if not _is_terminal(job.payload):
                    job.finish_now_requested_by = None
                    await self._notify_update(job)
                raise
            except OptimizerError as exc:
                if _is_terminal(job.payload):
                    return job, False
                job.finish_now_requested_by = None
                await self._notify_update(job)
                logger.warning("Optimizer finish-now request failed job_id=%s error=%s", job.id, exc)
                raise OptimizerError(f"The optimizer did not accept the finish-now request. {exc}") from exc
            # Terminal snapshots dominate stale control responses.
            if self._jobs.get(job.id) is job:
                job.observe(payload)
            if not _is_terminal(job.payload):
                await self._notify_update(job)
            return job, True

    async def cancel(self, session_id: str, job_id: str) -> SessionOptimization:
        """Cancel the displayed job without involving a model or another session's job."""
        job = self._jobs.get(job_id)
        if job is None or job.session_id != session_id:
            raise OptimizerJobUnavailable("Optimizer job not found.")
        if _is_terminal(job.payload) or job.payload.state == "cancelling":
            return job
        try:
            payload = await self._backend.cancel(job.remote_id)
        except OptimizerError as exc:
            # Completion can delete the remote job while cancellation is in flight.
            if _is_terminal(job.payload):
                return job
            logger.warning("Optimizer cancel request failed job_id=%s error=%s", job.id, exc)
            raise OptimizerError(f"The optimizer did not accept the cancel request. {exc}") from exc
        job.observe(payload)
        if self._jobs.get(job.id) is job and not _is_terminal(job.payload):
            await self._notify_update(job)
        return job

    async def _monitor(self, job: SessionOptimization) -> None:
        unreachable_since: float | None = None
        outage_reported = False
        cancellation_requested = False
        while not _is_terminal(job.payload):
            if job.retired.is_set() and not cancellation_requested:
                cancellation_requested = True
                await self._cancel_retired(job)
                if _is_terminal(job.payload):
                    break
            if cancellation_requested:
                await asyncio.sleep(self._poll_interval_seconds)
            else:
                try:
                    await asyncio.wait_for(job.retired.wait(), timeout=self._poll_interval_seconds)
                    continue
                except TimeoutError:
                    pass
            try:
                payload = await self._backend.get(job.remote_id)
            except asyncio.CancelledError:
                raise
            except OptimizerError as exc:
                # A status outage does not prove the remote job ended. Keep polling
                # live sessions until the optimizer reports a terminal state.
                now = asyncio.get_running_loop().time()
                if unreachable_since is None:
                    unreachable_since = now
                    logger.warning("Optimizer status check failed job_id=%s error=%s", job.id, exc)
                if not outage_reported and now - unreachable_since >= self._status_failure_grace_seconds:
                    logger.warning("Optimizer remains unreachable; retrying job_id=%s error=%s", job.id, exc)
                    outage_reported = True
                if self._jobs.get(job.id) is not job and outage_reported:
                    # The retired session has no result to preserve. Stop a cleanup
                    # monitor that cannot reach the remote optimizer.
                    return
                continue
            unreachable_since = None
            outage_reported = False
            previous = job.payload
            job.observe(payload)
            if job.payload != previous and not _is_terminal(job.payload):
                await self._notify_update(job)

    async def _relay_progress(self, job: SessionOptimization) -> None:
        try:
            async for progress in self._backend.progress_events(job.remote_id, job.client_address):
                if self._jobs.get(job.id) is not job:
                    return
                if self._on_update is not None:
                    await self._on_update(job.session_id, {"job_id": job.id, "progress": progress})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Optimizer progress relay failed job_id=%s", job.id)

    async def _complete(self, job: SessionOptimization) -> None:
        artifact_error: str | None = None
        artifact = None
        request_audit = None
        if self._jobs.get(job.id) is job and job.payload.state == "completed":
            try:
                artifact = await self._backend.result_artifact(job.payload)
                restored_content = await asyncio.to_thread(
                    restore_people_ids,
                    artifact.content,
                    job.original_id_by_anonymized_id,
                    job.people_count,
                )
                if len(restored_content) > self._max_result_bytes:
                    raise OptimizerResultError("The restored workbook exceeded the assistant download limit.")
                context = await asyncio.to_thread(build_result_context, job.schedule_yaml, workbook=restored_content)
                artifact = OptimizerArtifact(
                    restored_content,
                    artifact.filename,
                    artifact.media_type,
                    json.dumps(context, ensure_ascii=False, allow_nan=False).encode(),
                )
                if self._save_result is None:
                    await self._retain_artifact(job, artifact)
                if artifact is not None:
                    request_audit = await asyncio.to_thread(build_request_audit, job.schedule_yaml, restored_content)
            except (OptimizerError, OptimizerResultError) as exc:
                logger.warning("Optimizer result read failed job_id=%s error=%s", job.id, exc)
                artifact_error = str(exc)
                artifact = None
        if self._save_result is not None and self._jobs.get(job.id) is job:
            save_error = await self._save_result(job, artifact)
            job.artifact_saved = save_error is None and artifact is not None
            if save_error is not None:
                artifact_error = save_error
        job.schedule_yaml = ""
        job.submitted_yaml = ""
        await self._delete_retired(job)
        if self._jobs.get(job.id) is not job:
            return
        result_data = {
            **job.completion_details(),
            "job_id": job.id,
            "state": job.payload.state,
            "source_sha256": job.source_sha256,
            "result": job.payload.result,
            "error": job.payload.error,
            "download_available": job.artifact is not None or job.artifact_saved,
            "artifact_error": artifact_error,
        }
        if (job.artifact is not None or job.artifact_saved) and request_audit is not None:
            result_data["request_audit"] = request_audit
        await self._notify_update(job)
        if job.payload.state == "cancelled":
            return
        prompt = optimizer_completion_message(result_data)
        if self._jobs.get(job.id) is not job:
            return
        await self._on_completion(
            job.session_id, prompt, artifact if job.artifact_saved else job.artifact, job.model_selection
        )

    async def _retain_artifact(self, job: SessionOptimization, artifact: OptimizerArtifact) -> None:
        if self._jobs.get(job.id) is not job:
            return
        while self._artifact_order and (
            self._cached_artifact_bytes + artifact.retained_bytes > self._max_cached_result_bytes
        ):
            expired_id = self._artifact_order.pop(0)
            expired = self._jobs.get(expired_id)
            if expired is not None and expired.artifact is not None:
                self._cached_artifact_bytes -= expired.artifact.retained_bytes
                expired.artifact = None
        if artifact.retained_bytes <= self._max_cached_result_bytes:
            job.artifact = artifact
            self._artifact_order.append(job.id)
            self._cached_artifact_bytes += artifact.retained_bytes

    async def _notify_update(self, job: SessionOptimization) -> None:
        if self._on_update is None or self._jobs.get(job.id) is not job:
            return
        await self._on_update(
            job.session_id,
            {
                **job.completion_details(),
                "job_id": job.id,
                "state": job.payload.state,
                "terminal": _is_terminal(job.payload),
                "backend": job.backend,
                "request": job.request,
                "result": job.payload.result,
                "error": job.payload.error,
                "downloadable": job.artifact is not None or job.artifact_saved,
                "controls": job.payload.controls,
            },
        )

    def _latest(self, session_id: str) -> SessionOptimization | None:
        owner = self._sessions.get(session_id)
        return self._jobs.get(owner.latest) if owner is not None else None

    def _release_reservation(self, session_id: str, owner: OptimizerSession, reservation: object) -> None:
        if self._sessions.get(session_id) is not owner or owner.reservation is not reservation:
            return
        owner.reservation = None
        owner.runs -= 1
        if owner.runs == 0:
            self._sessions.pop(session_id)

    def _discard_session(self, session_id: str) -> None:
        """Release every run a session owns, including the ones it already replaced."""
        self._sessions.pop(session_id, None)
        for job_id in [job_id for job_id, job in self._jobs.items() if job.session_id == session_id]:
            job = self._jobs.pop(job_id)
            if job.artifact is not None:
                self._cached_artifact_bytes -= job.artifact.retained_bytes
                self._artifact_order.remove(job_id)

    def _start_task(self, coroutine: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)

        def finished(task: asyncio.Task[None]) -> None:
            self._tasks.discard(task)
            if not task.cancelled() and task.exception() is not None:
                logger.error("Optimizer lifecycle failed", exc_info=task.exception())

        task.add_done_callback(finished)
        return task


def _is_terminal(payload: OptimizerJobPayload) -> bool:
    return payload.terminal or payload.state in TERMINAL_STATES
