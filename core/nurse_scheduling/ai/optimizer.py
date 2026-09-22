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
import ipaddress
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, ValidationError

from .agent import AgentToolOutcome
from .optimizer_privacy import OptimizerResultError, prepare_optimizer_schedule, restore_people_ids

OPTIMIZER_TOOL = "optimizer"
WORKSPACE_OPTIMIZER_RESULT = "/workspace/optimizer-results/optimized-schedule.xlsx"
TERMINAL_STATES = frozenset({"completed", "cancelled", "failed"})
logger = logging.getLogger("nurse_scheduling.ai.optimizer")


class OptimizerError(Exception):
    """The configured optimizer transport or response failed."""


class OptimizerResultUnavailable(Exception):
    """A session-owned optimizer result is not available for download."""


class OptimizerJobPayload(BaseModel):
    """Subset of the optimizer job response used by the assistant."""

    id: str
    state: str
    terminal: bool = False
    queue_position: int | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    controls: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict)


class OptimizerBackend(Protocol):
    """Transport boundary used by session-scoped optimization jobs."""

    async def submit(self, schedule_yaml: str, timeout_seconds: int | None) -> OptimizerJobPayload: ...

    async def get(self, job_id: str) -> OptimizerJobPayload: ...

    async def finish_now(self, job_id: str) -> OptimizerJobPayload: ...

    async def cancel(self, job_id: str) -> OptimizerJobPayload: ...

    async def result_artifact(self, job: OptimizerJobPayload) -> "OptimizerArtifact": ...

    async def delete(self, job_id: str) -> None: ...

    async def close(self) -> None: ...


class HttpOptimizerBackend:
    """Call the existing optimizer HTTP API without exposing its credential to the model."""

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        request_timeout_seconds: float,
        max_result_bytes: int,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        endpoint = urlsplit(base_url)
        if auth_token and not (
            endpoint.scheme == "https" or (endpoint.scheme == "http" and _is_trusted_http_host(endpoint.hostname))
        ):
            raise ValueError("A credentialed optimizer endpoint must use HTTPS outside loopback or Docker Compose.")
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
        self._base_url = f"{base_url.rstrip('/')}/"
        self._client = httpx.AsyncClient(headers=headers, timeout=request_timeout_seconds, transport=transport)
        self._max_result_bytes = max_result_bytes

    async def submit(self, schedule_yaml: str, timeout_seconds: int | None) -> OptimizerJobPayload:
        fields: dict[str, tuple[None, str]] = {
            "yaml_content": (None, schedule_yaml),
            "prettify": (None, "true"),
        }
        if timeout_seconds is not None:
            fields["timeout"] = (None, str(timeout_seconds))
        return await self._request_job("POST", "optimize", files=fields)

    async def get(self, job_id: str) -> OptimizerJobPayload:
        return await self._request_job("GET", f"optimize/{job_id}")

    async def finish_now(self, job_id: str) -> OptimizerJobPayload:
        return await self._request_job("POST", f"optimize/{job_id}/finish-now")

    async def cancel(self, job_id: str) -> OptimizerJobPayload:
        return await self._request_job("POST", f"optimize/{job_id}/cancel")

    async def result_artifact(self, job: OptimizerJobPayload) -> "OptimizerArtifact":
        schedule_link = job.links.get("schedule")
        if not isinstance(schedule_link, str) or not _is_relative_link(schedule_link):
            raise OptimizerError("The optimizer did not provide a result download.")
        try:
            content = bytearray()
            async with self._client.stream("GET", urljoin(self._base_url, schedule_link.lstrip("/"))) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > self._max_result_bytes:
                        raise OptimizerError("The optimizer result exceeded the assistant download limit.")
                    content.extend(chunk)
        except httpx.HTTPError as exc:
            raise OptimizerError("The optimizer result could not be downloaded.") from exc
        if not content:
            raise OptimizerError("The optimizer returned an empty result.")
        return OptimizerArtifact(
            content=bytes(content),
            filename="optimized-schedule.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def delete(self, job_id: str) -> None:
        try:
            response = await self._client.delete(urljoin(self._base_url, f"optimize/{job_id}"))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OptimizerError("The optimizer job could not be deleted.") from exc

    async def _request_job(self, method: str, path: str, **kwargs: Any) -> OptimizerJobPayload:
        try:
            response = await self._client.request(method, urljoin(self._base_url, path), **kwargs)
            response.raise_for_status()
            return OptimizerJobPayload.model_validate(response.json())
        except httpx.HTTPError as exc:
            raise OptimizerError("The optimizer request failed.") from exc
        except (ValueError, ValidationError) as exc:
            raise OptimizerError("The optimizer returned an invalid job response.") from exc


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
    artifact: "OptimizerArtifact | None" = None


@dataclass(frozen=True)
class OptimizerArtifact:
    """A completed workbook retained for an authenticated browser download."""

    content: bytes
    filename: str
    media_type: str


CompletionCallback = Callable[[str, str, OptimizerArtifact | None], Awaitable[None]]
UpdateCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


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
        max_runs_per_session: int = 50,
        max_result_bytes: int = 10_000_000,
        max_cached_result_bytes: int = 100_000_000,
        max_schedule_bytes: int = 1_000_000,
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
        self._jobs: dict[str, SessionOptimization] = {}
        self._latest_by_session: dict[str, str] = {}
        self._starting: dict[str, object] = {}
        self._run_counts: dict[str, int] = {}
        self._artifact_order: list[str] = []
        self._cached_artifact_bytes = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    async def execute(self, session_id: str, schedule_yaml: str, arguments: str) -> AgentToolOutcome:
        """Execute the model-facing optimizer action."""
        try:
            raw = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return AgentToolOutcome("Optimizer arguments must be valid JSON.", False)
        if not isinstance(raw, dict):
            return AgentToolOutcome("Optimizer arguments must be a JSON object.", False)
        action = raw.get("action", "start")
        if action == "start":
            timeout = raw.get("timeout_seconds")
            if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0):
                return AgentToolOutcome("timeout_seconds must be a positive integer.", False)
            return await self._start(session_id, schedule_yaml, timeout)
        if action == "status":
            return await self._status(session_id)
        if action == "finish_now":
            return await self._finish_now(session_id)
        return AgentToolOutcome("action must be one of: start, status, finish_now.", False)

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._backend.close()

    async def result_artifact(self, session_id: str, job_id: str) -> OptimizerArtifact:
        """Return a completed artifact only to the session that started it."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.session_id != session_id:
                raise OptimizerResultUnavailable("Optimizer result not found.")
            if job.artifact is None:
                raise OptimizerResultUnavailable("This optimizer run has no downloadable result.")
            return job.artifact

    async def latest_result_artifact(self, session_id: str) -> OptimizerArtifact | None:
        """Return the newest finished workbook for a follow-up sandbox turn."""
        async with self._lock:
            for job in reversed(self._jobs.values()):
                # A run that is still going has no result yet, so an older workbook
                # remains current. A finished run without one makes every earlier
                # workbook stale, and mounting it would misreport the latest result.
                if job.session_id != session_id or not _is_terminal(job.payload):
                    continue
                return job.artifact
            return None

    def forget_session(self, session_id: str) -> None:
        """Drop every record of a retired chat session.

        The AI session store calls this synchronously while retiring a session, so it
        only rebinds state that the lock-holding coroutines never mutate across an await.
        """
        self._starting.pop(session_id, None)
        for job in self._jobs.values():
            if job.session_id == session_id and not _is_terminal(job.payload):
                self._start_task(self._cancel_retired(job))
        self._discard_session(session_id)

    async def _start(self, session_id: str, schedule_yaml: str, timeout_seconds: int | None) -> AgentToolOutcome:
        try:
            prepared = await asyncio.to_thread(prepare_optimizer_schedule, schedule_yaml, self._max_schedule_bytes)
        except ValueError as exc:
            return AgentToolOutcome(f"The optimizer requires a valid frontend schedule. {exc}", False)
        async with self._lock:
            if (
                session_id not in self._latest_by_session
                and session_id not in self._starting
                and len(set(self._latest_by_session) | set(self._starting)) >= self._max_sessions
            ):
                return AgentToolOutcome("The optimizer session limit has been reached.", False)
            if self._run_counts.get(session_id, 0) >= self._max_runs_per_session:
                return AgentToolOutcome(
                    f"This chat session has reached its limit of {self._max_runs_per_session} optimizer runs.",
                    False,
                )
            if session_id in self._starting:
                return AgentToolOutcome("An optimizer run for this chat session is already being submitted.", False)
            current = self._latest(session_id)
            if current is not None and not _is_terminal(current.payload):
                return AgentToolOutcome(
                    f"Optimizer job {current.id} is already {current.payload.state}. Check it or finish it now.",
                    False,
                )
            # Reserve the run, then submit without the shared lock. Remote submission
            # would otherwise serialize starts, retention, and downloads across sessions.
            reservation = object()
            self._starting[session_id] = reservation
            self._run_counts[session_id] = self._run_counts.get(session_id, 0) + 1
        try:
            payload = await self._backend.submit(
                prepared.submission_yaml,
                self._default_timeout_seconds if timeout_seconds is None else timeout_seconds,
            )
        except OptimizerError as exc:
            logger.warning("Optimizer submission failed: %s", exc)
            self._release_reservation(session_id, reservation)
            return AgentToolOutcome("The optimizer could not accept the schedule.", False)
        except BaseException:
            # A stopped turn cancels this call, and keeping the reservation would leave
            # the session unable to start another run.
            self._release_reservation(session_id, reservation)
            raise
        async with self._lock:
            retired = self._starting.get(session_id) is not reservation
            if not retired:
                self._starting.pop(session_id)
            job = SessionOptimization(
                id=f"opt_{uuid4().hex}",
                session_id=session_id,
                remote_id=payload.id,
                source_sha256=hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest(),
                payload=payload,
                original_id_by_anonymized_id=prepared.original_id_by_anonymized_id,
                people_count=prepared.people_count,
            )
            if not retired:
                self._jobs[job.id] = job
                self._latest_by_session[session_id] = job.id
            if _is_terminal(payload):
                self._start_task(self._complete(job))
            else:
                self._start_task(self._monitor(job))
        if retired:
            if not _is_terminal(payload):
                self._start_task(self._cancel_retired(job))
            return AgentToolOutcome("This chat session expired while the optimizer job was starting.", False)
        if not _is_terminal(job.payload):
            await self._notify_update(job)
        return AgentToolOutcome(
            f"Started optimizer job {job.id} in the background for schedule SHA-256 {job.source_sha256}. "
            "The assistant will be woken when it finishes. The user can keep chatting meanwhile.",
            True,
        )

    async def _status(self, session_id: str) -> AgentToolOutcome:
        job = self._latest(session_id)
        if job is None:
            return AgentToolOutcome("No optimizer job has been started in this chat session.", False)
        return AgentToolOutcome(_job_summary(job), True)

    async def _cancel_retired(self, job: SessionOptimization) -> None:
        try:
            payload = await self._backend.cancel(job.remote_id)
        except OptimizerError as exc:
            logger.warning("Optimizer cancellation failed job_id=%s error=%s", job.id, exc)
            return
        async with self._lock:
            if not _is_terminal(job.payload):
                job.payload = payload

    async def _finish_now(self, session_id: str) -> AgentToolOutcome:
        job = self._latest(session_id)
        if job is None:
            return AgentToolOutcome("No optimizer job has been started in this chat session.", False)
        if _is_terminal(job.payload):
            return AgentToolOutcome(_job_summary(job), True)
        try:
            payload = await self._backend.finish_now(job.remote_id)
        except OptimizerError as exc:
            logger.warning("Optimizer finish-now request failed job_id=%s error=%s", job.id, exc)
            return AgentToolOutcome("The optimizer did not accept the finish-now request.", False)
        async with self._lock:
            # Polling can reach a terminal state while this request is in flight. Keeping
            # the older snapshot would block the session from ever starting another run.
            if self._jobs.get(job.id) is job and not _is_terminal(job.payload):
                job.payload = payload
        if not _is_terminal(job.payload):
            await self._notify_update(job)
        return AgentToolOutcome(
            f"Asked optimizer job {job.id} to finish with its best available result. Current state: {job.payload.state}.",
            True,
        )

    async def _monitor(self, job: SessionOptimization) -> None:
        unreachable_since: float | None = None
        while not _is_terminal(job.payload):
            await asyncio.sleep(self._poll_interval_seconds)
            try:
                payload = await self._backend.get(job.remote_id)
            except asyncio.CancelledError:
                raise
            except OptimizerError as exc:
                # Give up only after a sustained outage. A remote run keeps going after a
                # short status failure, and reporting it as finished abandons its result.
                now = asyncio.get_running_loop().time()
                if unreachable_since is None:
                    unreachable_since = now
                    logger.warning("Optimizer status check failed job_id=%s error=%s", job.id, exc)
                if now - unreachable_since >= self._status_failure_grace_seconds:
                    logger.warning("Optimizer became unreachable job_id=%s error=%s", job.id, exc)
                    async with self._lock:
                        if not _is_terminal(job.payload):
                            job.payload = OptimizerJobPayload(
                                id=job.remote_id,
                                state="failed",
                                terminal=True,
                                error={"code": "optimizer_unreachable", "message": str(exc)},
                            )
                continue
            unreachable_since = None
            async with self._lock:
                if not _is_terminal(job.payload):
                    job.payload = payload
        await self._complete(job)

    async def _complete(self, job: SessionOptimization) -> None:
        artifact_error: str | None = None
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
                artifact = OptimizerArtifact(restored_content, artifact.filename, artifact.media_type)
                await self._retain_artifact(job, artifact)
            except (OptimizerError, OptimizerResultError) as exc:
                logger.warning("Optimizer result read failed job_id=%s error=%s", job.id, exc)
                artifact_error = str(exc)
        try:
            await self._backend.delete(job.remote_id)
        except OptimizerError as exc:
            logger.warning("Optimizer cleanup failed job_id=%s error=%s", job.id, exc)
        if self._jobs.get(job.id) is not job:
            return
        result_data = {
            "job_id": job.id,
            "state": job.payload.state,
            "source_sha256": job.source_sha256,
            "result": job.payload.result,
            "error": job.payload.error,
            "download_available": job.artifact is not None,
            "artifact_error": artifact_error,
        }
        await self._notify_update(job)
        result_path = WORKSPACE_OPTIMIZER_RESULT if job.artifact is not None else "unavailable"
        prompt = (
            f"Optimizer job finished. Result workbook: {result_path}.\n"
            f"Optimizer result JSON:\n{json.dumps(result_data, ensure_ascii=False)}"
        )
        if self._jobs.get(job.id) is not job:
            return
        await self._on_completion(job.session_id, prompt, job.artifact)

    async def _retain_artifact(self, job: SessionOptimization, artifact: OptimizerArtifact) -> None:
        async with self._lock:
            if self._jobs.get(job.id) is not job:
                return
            while self._artifact_order and (
                self._cached_artifact_bytes + len(artifact.content) > self._max_cached_result_bytes
            ):
                expired_id = self._artifact_order.pop(0)
                expired = self._jobs.get(expired_id)
                if expired is not None and expired.artifact is not None:
                    self._cached_artifact_bytes -= len(expired.artifact.content)
                    expired.artifact = None
            if len(artifact.content) <= self._max_cached_result_bytes:
                job.artifact = artifact
                self._artifact_order.append(job.id)
                self._cached_artifact_bytes += len(artifact.content)

    async def _notify_update(self, job: SessionOptimization) -> None:
        if self._on_update is None or self._jobs.get(job.id) is not job:
            return
        await self._on_update(
            job.session_id,
            {
                "job_id": job.id,
                "state": job.payload.state,
                "terminal": _is_terminal(job.payload),
                "result": job.payload.result,
                "error": job.payload.error,
                "downloadable": job.artifact is not None,
            },
        )

    def _latest(self, session_id: str) -> SessionOptimization | None:
        job_id = self._latest_by_session.get(session_id)
        return self._jobs.get(job_id) if job_id is not None else None

    def _release_reservation(self, session_id: str, reservation: object) -> None:
        """Return the run reserved for a submission that never produced a job.

        Rebinding this bookkeeping never spans an await, so it stays consistent for the
        lock holders and remains available while a cancelled call unwinds.
        """
        if self._starting.get(session_id) is not reservation:
            return
        self._starting.pop(session_id)
        remaining = self._run_counts.get(session_id, 1) - 1
        if remaining > 0:
            self._run_counts[session_id] = remaining
        else:
            self._run_counts.pop(session_id, None)

    def _discard_session(self, session_id: str) -> None:
        """Release every run a session owns, including the ones it already replaced."""
        self._latest_by_session.pop(session_id, None)
        self._run_counts.pop(session_id, None)
        for job_id in [job_id for job_id, job in self._jobs.items() if job.session_id == session_id]:
            job = self._jobs.pop(job_id)
            if job.artifact is not None:
                self._cached_artifact_bytes -= len(job.artifact.content)
                self._artifact_order.remove(job_id)

    def _start_task(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def optimizer_tool_definition(default_timeout_seconds: int = 300) -> dict[str, Any]:
    """Return the single model-facing contract for optimizer lifecycle actions."""
    return {
        "type": "function",
        "function": {
            "name": OPTIMIZER_TOOL,
            "description": (
                "Start the scheduling optimizer on the current working YAML, inspect its background status, or ask "
                "a running optimizer to finish with its best available solution. Start returns immediately. "
                f"A completed workbook is available at {WORKSPACE_OPTIMIZER_RESULT} in the next assistant turn. "
                "Omit timeout_seconds to use the configured default."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["start", "status", "finish_now"]},
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "description": f"Optional optimizer time limit in seconds. Default: {default_timeout_seconds} seconds.",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    }


def _is_trusted_http_host(host: str | None) -> bool:
    """Allow cleartext credentials only on loopback or the Compose service name."""
    if host in {"localhost", "api"}:
        return True
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_relative_link(link: str) -> bool:
    """Keep a result download on the configured optimizer, which holds its bearer token."""
    parsed = urlsplit(link)
    return bool(link) and not parsed.scheme and not parsed.netloc


def _is_terminal(payload: OptimizerJobPayload) -> bool:
    return payload.terminal or payload.state in TERMINAL_STATES


def _job_summary(job: SessionOptimization) -> str:
    details = job.payload.result or job.payload.error
    suffix = f" Result: {json.dumps(details, ensure_ascii=False)}" if details else ""
    return f"Optimizer job {job.id} is {job.payload.state}.{suffix}"
