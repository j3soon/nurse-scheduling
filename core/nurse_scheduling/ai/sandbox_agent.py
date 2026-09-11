"""One-turn shell agent over a disposable provider-neutral sandbox."""

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
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from .agent import AgentEvent, AgentProposal, AgentToolBatchMetrics, AgentToolOutcome, AgentToolUse, run_tool_agent
from .candidate import SCHEDULE_FILENAME, review_schedule_candidate
from .config import AiSettings
from .pi.read import READ_TOOL
from .provider import ChatMessage, ToolCapableChatProvider
from .sandbox import (
    SandboxBackend,
    SandboxError,
    SandboxFactory,
    SandboxFileNotFoundError,
    SandboxLifecycleMetrics,
    managed_sandbox,
)
from .sandbox_tools import SandboxPiTools
from .schema import (
    SCHEMA_REFERENCE_FILES,
    TAIWAN_HOLIDAYS_SOURCE,
    load_schedule_reference,
    load_taiwan_holidays_reference,
)

logger = logging.getLogger("nurse_scheduling.ai.sandbox_agent")
WORKSPACE_SCHEDULE = f"/workspace/{SCHEDULE_FILENAME}"
WORKSPACE_PENDING_PROPOSAL = "/workspace/pending-proposal.yaml"
WORKSPACE_PENDING_DIFF = "/workspace/pending-proposal.diff"
REFERENCE_SCHEMAS = {group: f"/reference/{path.name}" for group, path in SCHEMA_REFERENCE_FILES.items()}
REFERENCE_SCHEMAS["taiwan-holidays"] = f"/reference/{TAIWAN_HOLIDAYS_SOURCE.name}"

SYSTEM_PROMPT_PATH = Path(__file__).with_name("prompts") / "sandbox-system.md"
SANDBOX_SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").rstrip("\n")


class SandboxCandidateError(SandboxError):
    """The final untrusted schedule failed trusted server-side review."""


class SandboxTurnTimeoutError(SandboxError):
    """The complete disposable agent turn exceeded its deadline."""


@dataclass(frozen=True)
class AgentScheduleChange:
    """A server-validated working copy safe to preview in the UI."""

    schedule_yaml: str


@dataclass(frozen=True)
class SandboxAgentLimits:
    """Trusted orchestration and AI-context limits for one sandbox turn."""

    max_schedule_bytes: int
    turn_timeout_seconds: float
    cleanup_timeout_seconds: float
    bash_command_timeout_seconds: float
    max_tool_rounds: int
    max_tool_calls: int

    @classmethod
    def from_settings(cls, settings: AiSettings) -> "SandboxAgentLimits":
        """Collect sandbox-turn limits from validated application settings."""
        return cls(
            max_schedule_bytes=settings.max_schedule_bytes,
            turn_timeout_seconds=settings.sandbox_turn_timeout_seconds,
            cleanup_timeout_seconds=settings.sandbox_cleanup_timeout_seconds,
            bash_command_timeout_seconds=settings.sandbox_command_timeout_seconds,
            max_tool_rounds=settings.agent_max_tool_rounds,
            max_tool_calls=settings.agent_max_tool_calls,
        )


@dataclass
class SandboxTurnMetrics:
    """Measured lifecycle and operation time for one disposable sandbox."""

    provisioning_seconds: float = 0.0
    execution_seconds: float = 0.0
    pause_transition_seconds: float = 0.0
    warm_waiting_seconds: float = 0.0
    suspended_seconds: float = 0.0
    resume_wait_seconds: float = 0.0
    max_resume_wait_seconds: float = 0.0
    teardown_seconds: float = 0.0
    lifetime_seconds: float = 0.0
    pause_count: int = 0
    pause_cancel_count: int = 0
    resume_count: int = 0


@asynccontextmanager
async def _measured_sandbox_turn(
    factory: SandboxFactory,
    cleanup_timeout_seconds: float,
    metrics: SandboxTurnMetrics,
    schedule_yaml: str,
    pending_proposal_yaml: str,
    pending_proposal_diff: str,
) -> AsyncIterator[SandboxBackend]:
    """Create, hydrate, and measure a sandbox only when its first tool batch begins."""
    stack = AsyncExitStack()
    sandbox = _LazySandboxTurn(
        factory,
        cleanup_timeout_seconds,
        metrics,
        stack,
        schedule_yaml,
        pending_proposal_yaml,
        pending_proposal_diff,
    )
    try:
        async with stack:
            try:
                yield sandbox
            finally:
                sandbox.mark_cleanup_started()
    finally:
        sandbox.finish_metrics()


class _LazySandboxTurn:
    """Sandbox protocol adapter that defers allocation until tool execution."""

    def __init__(
        self,
        factory: SandboxFactory,
        cleanup_timeout_seconds: float,
        metrics: SandboxTurnMetrics,
        stack: AsyncExitStack,
        schedule_yaml: str,
        pending_proposal_yaml: str,
        pending_proposal_diff: str,
    ) -> None:
        self._factory = factory
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._metrics = metrics
        self._stack = stack
        self._schedule_yaml = schedule_yaml
        self._pending_proposal_yaml = pending_proposal_yaml
        self._pending_proposal_diff = pending_proposal_diff
        self._sandbox: SandboxBackend | None = None
        self._lifecycle_started: float | None = None
        self._cleanup_started: float | None = None

    @property
    def started(self) -> bool:
        return self._sandbox is not None

    @property
    def sandbox_id(self) -> str:
        return self._require_sandbox().sandbox_id

    async def _start(self) -> SandboxBackend:
        if self._sandbox is not None:
            return self._sandbox
        self._lifecycle_started = time.perf_counter()
        try:
            self._sandbox = await self._stack.enter_async_context(
                managed_sandbox(self._factory, cleanup_timeout_seconds=self._cleanup_timeout_seconds)
            )
        finally:
            self._metrics.provisioning_seconds = time.perf_counter() - self._lifecycle_started
        await hydrate_sandbox(
            self._sandbox,
            self._schedule_yaml,
            self._pending_proposal_yaml,
            self._pending_proposal_diff,
        )
        return self._sandbox

    def _require_sandbox(self) -> SandboxBackend:
        if self._sandbox is None:  # pragma: no cover - callers start before synchronous access
            raise RuntimeError("sandbox has not started")
        return self._sandbox

    @asynccontextmanager
    async def activity_batch(self) -> AsyncIterator[None]:
        sandbox = await self._start()
        async with sandbox.activity_batch():
            yield

    async def write_file(self, path: str, content: str | bytes) -> None:
        await (await self._start()).write_file(path, content)

    async def read_file(self, path: str) -> bytes:
        return await (await self._start()).read_file(path)

    async def run(self, command: str, *, timeout_seconds: float | None = None):
        return await (await self._start()).run(command, timeout_seconds=timeout_seconds)

    async def close(self) -> None:
        """Let the owning exit stack close the underlying sandbox."""

    def mark_cleanup_started(self) -> None:
        if self.started:
            self._cleanup_started = time.perf_counter()

    def finish_metrics(self) -> None:
        if self._lifecycle_started is None:
            return
        now = time.perf_counter()
        self._metrics.lifetime_seconds = now - self._lifecycle_started
        if self._cleanup_started is not None:
            self._metrics.teardown_seconds = now - self._cleanup_started

        lifecycle = getattr(self._sandbox, "lifecycle_metrics", SandboxLifecycleMetrics())
        self._metrics.execution_seconds = lifecycle.execution_seconds
        self._metrics.pause_count = lifecycle.pause_count
        self._metrics.pause_cancel_count = lifecycle.pause_cancel_count
        self._metrics.pause_transition_seconds = lifecycle.pause_transition_seconds
        self._metrics.resume_count = lifecycle.resume_count
        self._metrics.resume_wait_seconds = lifecycle.resume_wait_seconds
        self._metrics.max_resume_wait_seconds = lifecycle.max_resume_wait_seconds
        self._metrics.suspended_seconds = lifecycle.suspended_seconds
        if lifecycle.teardown_seconds > 0:
            self._metrics.teardown_seconds = lifecycle.teardown_seconds
        accounted_seconds = (
            self._metrics.provisioning_seconds
            + self._metrics.execution_seconds
            + self._metrics.pause_transition_seconds
            + self._metrics.suspended_seconds
            + self._metrics.resume_wait_seconds
            + self._metrics.teardown_seconds
        )
        self._metrics.warm_waiting_seconds = max(0.0, self._metrics.lifetime_seconds - accounted_seconds)


async def run_sandbox_agent(
    provider: ToolCapableChatProvider,
    factory: SandboxFactory,
    schedule_yaml: str,
    messages: Sequence[ChatMessage],
    limits: SandboxAgentLimits,
    metrics: SandboxTurnMetrics | None = None,
    observe_tool_batch: Callable[[AgentToolBatchMetrics], None] | None = None,
    take_steering: Callable[[bool], Sequence[tuple[str, str]]] | None = None,
    pending_proposal_yaml: str = "",
    pending_proposal_diff: str = "",
) -> AsyncIterator[AgentEvent | AgentScheduleChange]:
    """Hydrate, run, read, validate, and destroy one fresh sandbox turn."""
    metrics = metrics or SandboxTurnMetrics()
    try:
        async with asyncio.timeout(limits.turn_timeout_seconds):
            async with _measured_sandbox_turn(
                factory,
                limits.cleanup_timeout_seconds,
                metrics,
                schedule_yaml,
                pending_proposal_yaml,
                pending_proposal_diff,
            ) as sandbox:
                sandbox_tools = SandboxPiTools(sandbox, limits.bash_command_timeout_seconds)
                candidate_tracker = _ScheduleCandidateTracker(
                    sandbox,
                    schedule_yaml,
                    limits.max_schedule_bytes,
                )
                pending_schedule_change: str | None = None

                async def execute_command(name: str, arguments: str) -> AgentToolOutcome:
                    nonlocal pending_schedule_change
                    pending_schedule_change = None
                    outcome = await sandbox_tools.execute(name, arguments)
                    if name == READ_TOOL:
                        return outcome
                    candidate_status = await candidate_tracker.review_if_changed()
                    if candidate_status is None:
                        return outcome
                    validation, pending_schedule_change = candidate_status
                    return AgentToolOutcome(
                        f"{outcome.text}\n\n{validation.text}",
                        outcome.ok and validation.ok,
                    )

                async for event in run_tool_agent(
                    provider,
                    messages,
                    sandbox_tools.definitions,
                    execute_command,
                    activity_batch=sandbox.activity_batch,
                    parallel_tool_names=frozenset({READ_TOOL}),
                    observe_tool_batch=observe_tool_batch,
                    take_steering=take_steering,
                    max_tool_rounds=limits.max_tool_rounds,
                    max_tool_calls=limits.max_tool_calls,
                ):
                    yield event
                    if isinstance(event, AgentToolUse) and pending_schedule_change is not None:
                        yield AgentScheduleChange(pending_schedule_change)
                        pending_schedule_change = None

                if not sandbox.started:
                    return
                candidate = await _read_candidate(sandbox, limits.max_schedule_bytes)
                review = review_schedule_candidate(schedule_yaml, candidate, limits.max_schedule_bytes)
                logger.info(
                    "sandbox candidate validated sandbox_id=%s valid=%s proposal=%s",
                    sandbox.sandbox_id,
                    review.outcome.ok,
                    review.proposal is not None,
                )
                if not review.outcome.ok:
                    raise SandboxCandidateError("The sandbox candidate failed trusted schedule validation.")
                if review.proposal is not None:
                    yield AgentProposal(review.proposal.text, review.proposal.diff.render())
    except TimeoutError as exc:
        raise SandboxTurnTimeoutError(
            f"The sandbox agent turn exceeded its {limits.turn_timeout_seconds:g}-second limit."
        ) from exc
    finally:
        logger.info(
            "sandbox timing lifetime_seconds=%.3f provisioning_seconds=%.3f execution_seconds=%.3f "
            "pause_transition_seconds=%.3f warm_waiting_seconds=%.3f suspended_seconds=%.3f "
            "resume_wait_seconds=%.3f teardown_seconds=%.3f pause_count=%s pause_cancel_count=%s resume_count=%s",
            metrics.lifetime_seconds,
            metrics.provisioning_seconds,
            metrics.execution_seconds,
            metrics.pause_transition_seconds,
            metrics.warm_waiting_seconds,
            metrics.suspended_seconds,
            metrics.resume_wait_seconds,
            metrics.teardown_seconds,
            metrics.pause_count,
            metrics.pause_cancel_count,
            metrics.resume_count,
        )


async def hydrate_sandbox(
    sandbox: SandboxBackend,
    schedule_yaml: str,
    pending_proposal_yaml: str = "",
    pending_proposal_diff: str = "",
) -> None:
    """Copy trusted application state and searchable references into one turn."""
    started = time.perf_counter()
    await sandbox.write_file(WORKSPACE_SCHEDULE, schedule_yaml)
    if pending_proposal_yaml:
        await sandbox.write_file(WORKSPACE_PENDING_PROPOSAL, pending_proposal_yaml)
        await sandbox.write_file(WORKSPACE_PENDING_DIFF, pending_proposal_diff)
    for group, path in REFERENCE_SCHEMAS.items():
        reference = load_taiwan_holidays_reference() if group == "taiwan-holidays" else load_schedule_reference(group)
        if reference is None:  # pragma: no cover - constants are defined together
            raise ValueError(f"unknown schedule reference group: {group}")
        await sandbox.write_file(path, reference)
    logger.info(
        "sandbox hydrated sandbox_id=%s schedule_bytes=%s latency_seconds=%.3f",
        sandbox.sandbox_id,
        len(schedule_yaml.encode("utf-8")),
        time.perf_counter() - started,
    )


async def _read_candidate(sandbox: SandboxBackend, max_schedule_bytes: int) -> str:
    started = time.perf_counter()
    try:
        candidate = await sandbox.read_file(WORKSPACE_SCHEDULE)
    except SandboxFileNotFoundError as exc:
        # The model owns the working copy and can delete it, which is a failed
        # turn rather than a sandbox failure.
        raise SandboxCandidateError(f"The sandbox working copy {WORKSPACE_SCHEDULE} no longer exists.") from exc
    logger.info(
        "sandbox candidate read sandbox_id=%s candidate_bytes=%s latency_seconds=%.3f",
        sandbox.sandbox_id,
        len(candidate),
        time.perf_counter() - started,
    )
    if len(candidate) > max_schedule_bytes:
        raise SandboxCandidateError(f"The sandbox candidate exceeds the {max_schedule_bytes}-byte schedule limit.")
    try:
        return candidate.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SandboxCandidateError("The sandbox candidate is not valid UTF-8.") from exc


class _ScheduleCandidateTracker:
    """Give the model trusted validation feedback after a shell edit."""

    def __init__(self, sandbox: SandboxBackend, base_text: str, max_bytes: int) -> None:
        self._sandbox = sandbox
        self._base_text = base_text
        self._max_bytes = max_bytes
        self._last_content = base_text.encode("utf-8")

    async def review_if_changed(self) -> tuple[AgentToolOutcome, str | None] | None:
        prefix = "Trusted schedule check after this command:"
        try:
            content = await self._sandbox.read_file(WORKSPACE_SCHEDULE)
        except SandboxFileNotFoundError:
            # Report the deletion to the model instead of failing the turn, so it
            # can restore the working copy it removed.
            return (
                AgentToolOutcome(
                    f"{prefix}\nThe working copy {WORKSPACE_SCHEDULE} no longer exists. "
                    "Restore it before finishing this turn.",
                    False,
                ),
                None,
            )
        if content == self._last_content:
            return None
        self._last_content = content
        if len(content) > self._max_bytes:
            return (
                AgentToolOutcome(
                    f"{prefix}\nThe candidate exceeds the {self._max_bytes}-byte schedule limit.",
                    False,
                ),
                None,
            )
        try:
            candidate = content.decode("utf-8")
        except UnicodeDecodeError:
            return (
                AgentToolOutcome(f"{prefix}\nThe candidate is not valid UTF-8.", False),
                None,
            )

        review = review_schedule_candidate(self._base_text, candidate, self._max_bytes)
        logger.info(
            "sandbox intermediate candidate validated sandbox_id=%s valid=%s proposal=%s",
            self._sandbox.sandbox_id,
            review.outcome.ok,
            review.proposal is not None,
        )
        if review.proposal is not None:
            return (
                AgentToolOutcome(
                    f"{prefix}\nThe candidate passed trusted server-side validation and differs from the base schedule.",
                    True,
                ),
                candidate,
            )
        guidance = ""
        if not review.outcome.ok:
            guidance = (
                "The working copy retains this command's changes. Repair the reported problems before finishing.\n"
            )
        return (
            AgentToolOutcome(f"{prefix}\n{guidance}{review.outcome.text}", review.outcome.ok),
            candidate if review.outcome.ok else None,
        )
