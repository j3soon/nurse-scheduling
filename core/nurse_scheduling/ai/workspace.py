"""Disposable sandbox workspace, hydration, and candidate validation."""

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

# This file is mostly AI generated.

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from .agent_types import AgentToolResult
from .candidate import SCHEDULE_FILENAME, PendingProposal, review_schedule_candidate
from .config import AiSettings
from .downloads import WORKSPACE_DOWNLOAD, validate_download_zip
from .optimizer import WORKSPACE_OPTIMIZER_RESULT
from .result_context import build_result_context
from .sandbox import (
    SandboxBackend,
    SandboxError,
    SandboxFactory,
    SandboxFileNotFoundError,
    SandboxFileSizeError,
    SandboxLifecycleMetrics,
    managed_sandbox,
)
from .schema import (
    SCHEMA_REFERENCE_FILES,
    TAIWAN_HOLIDAYS_SOURCE,
    load_schedule_reference,
    load_taiwan_holidays_reference,
    load_user_guide_references,
)
from .system_prompt import compose_system_prompt

logger = logging.getLogger("nurse_scheduling.ai.workspace")
WORKSPACE_SCHEDULE = f"/workspace/{SCHEDULE_FILENAME}"
WORKSPACE_PENDING_PROPOSAL = "/workspace/pending-proposal.yaml"
WORKSPACE_PENDING_DIFF = "/workspace/pending-proposal.diff"
WORKSPACE_ATTACHMENTS = "/workspace/attachments"
REFERENCE_SCHEMAS = {group: f"/reference/{path.name}" for group, path in SCHEMA_REFERENCE_FILES.items()}
REFERENCE_SCHEMAS["taiwan-holidays"] = f"/reference/{TAIWAN_HOLIDAYS_SOURCE.name}"
REFERENCE_USER_GUIDE = "/reference/user-guide"
ATTACHMENT_TOOL_DIRECTORY = Path(__file__).with_name("attachment_tools")
INSPECTION_HELPERS = {
    "inspect_request_tiers.py": "Current YAML inventory of all nonzero shift-request weight tiers, with entry and expanded target counts. --max-tiers bounds returned tiers.",
    "inspect_shift_requests.py": "Current YAML nonzero shift-request counts and resolved selectors. Repeat --weight, --person or --date to filter. --max-requests 0 returns counts only.",
    "inspect_xlsx.py": "XLSX inspection. Use --overview for up to 100 sheet names, visibility states, and reported sizes without reading cells. Otherwise inspect bounded cells, formulas, and saved caches. Add --styles for stored font/fill colors, borders, alignment, and number formats.",
    "inspect_pdf.py": "PDF page text and rendered page images. Use --find TEXT for bounded literal search with matching page numbers and excerpts. Reports search truncation and pages without text. No OCR.",
    "inspect_optimizer_result.py": "Optimizer assignments, signed request counts and available staffing/succession audits using a compiled schedule context.",
}
REFERENCE_ATTACHMENT_TOOLS = {
    f"/reference/tools/{name}": ATTACHMENT_TOOL_DIRECTORY / name for name in INSPECTION_HELPERS
}
WORKSPACE_SOURCE_CONTEXT = "/workspace/schedule-context.json"
WORKSPACE_RESULT_CONTEXT = "/workspace/optimizer-results/schedule-context.json"
WORKSPACE_PENDING_RESULT_CONTEXT = "/workspace/optimizer-results/pending-schedule-context.json"


def inspection_helper_catalog() -> str:
    """Advertise only the inspection scripts hydrated by this server."""
    return (
        "# Inspection helpers\n\n"
        + "\n".join(
            f"- `/reference/tools/{name}`: {description} Run with `--help` for usage."
            for name, description in INSPECTION_HELPERS.items()
        )
        + "\n\nThe result reader supports exported roster cells with bracketed annotations. Other layouts or decorations need a custom parser.\n"
        + "\nAssignment query: `python /reference/tools/inspect_optimizer_result.py --source-sha256 <completion hash> --person <exact ID> --date <YYYY-MM-DD>`. Person and date filters are repeatable. Omitted filters select the full dimension, with bounded output.\n"
    )


SANDBOX_SYSTEM_PROMPT = compose_system_prompt()


@dataclass(frozen=True)
class AgentDownload:
    """One validated ZIP captured before sandbox cleanup."""

    content: bytes


class SandboxDownloadError(SandboxError):
    """The generated ZIP could not be captured safely."""


class SandboxDownloadValidationError(SandboxDownloadError):
    """The agent generated a ZIP that violates the download contract."""


class SandboxCandidateError(SandboxError):
    """The final untrusted schedule failed trusted server-side review."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message


class SandboxCommandTimeoutError(SandboxError):
    """A command timeout terminated the sandbox and the remaining run."""


class SandboxRunTimeoutError(SandboxError):
    """The complete disposable agent run exceeded its deadline."""


@dataclass(frozen=True)
class AgentScheduleChange:
    """A server-validated working copy safe to preview in the UI."""

    schedule_yaml: str


@dataclass(frozen=True)
class SandboxAttachment:
    """One bounded untrusted file copied into a disposable sandbox."""

    filename: str
    media_type: str
    data: bytes
    id: str = ""


@dataclass(frozen=True)
class WorkspaceInputs:
    """Immutable session schedule and optional files captured for one run."""

    schedule_yaml: str
    pending_proposal: PendingProposal | None = None
    attachments: tuple[SandboxAttachment, ...] = ()
    optimizer_result: bytes | None = None
    # Compiled selectors of the schedule the optimizer received, built when the job completed.
    optimizer_context: bytes | None = None


@dataclass(frozen=True)
class WorkspaceLimits:
    """Trusted orchestration and AI-context limits for one workspace run."""

    max_schedule_bytes: int
    run_timeout_seconds: float
    cleanup_timeout_seconds: float
    bash_command_timeout_seconds: float
    max_tool_rounds: int
    max_tool_calls: int
    optimizer_default_timeout_seconds: int = 300
    max_download_bytes: int = 50_000_000

    @classmethod
    def from_settings(cls, settings: AiSettings) -> "WorkspaceLimits":
        """Collect workspace run limits from validated application settings."""
        return cls(
            max_schedule_bytes=settings.max_schedule_bytes,
            max_download_bytes=settings.max_download_bytes,
            run_timeout_seconds=settings.sandbox_turn_timeout_seconds,
            cleanup_timeout_seconds=settings.sandbox_cleanup_timeout_seconds,
            bash_command_timeout_seconds=settings.sandbox_command_timeout_seconds,
            max_tool_rounds=settings.agent_max_tool_rounds,
            max_tool_calls=settings.agent_max_tool_calls,
            optimizer_default_timeout_seconds=settings.optimizer_default_timeout_seconds,
        )


@dataclass
class SandboxRunMetrics:
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
async def sandbox_workspace(
    factory: SandboxFactory,
    cleanup_timeout_seconds: float,
    metrics: SandboxRunMetrics,
    inputs: WorkspaceInputs,
) -> AsyncIterator["SandboxWorkspace"]:
    """Create, hydrate, and measure a sandbox only when its first tool batch begins."""
    stack = AsyncExitStack()
    sandbox = SandboxWorkspace(
        factory,
        cleanup_timeout_seconds,
        metrics,
        stack,
        inputs,
    )
    try:
        async with stack:
            try:
                yield sandbox
            finally:
                sandbox.mark_cleanup_started()
    finally:
        sandbox.finish_metrics()


class SandboxWorkspace:
    """Sandbox protocol adapter that defers allocation until tool execution."""

    def __init__(
        self,
        factory: SandboxFactory,
        cleanup_timeout_seconds: float,
        metrics: SandboxRunMetrics,
        stack: AsyncExitStack,
        inputs: WorkspaceInputs,
    ) -> None:
        self._factory = factory
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._metrics = metrics
        self._stack = stack
        self._inputs = inputs
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
        await hydrate_sandbox(self._sandbox, self._inputs)
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

    async def write_files(self, files: Mapping[str, str | bytes]) -> None:
        await (await self._start()).write_files(files)

    async def read_file(self, path: str, *, max_bytes: int | None = None) -> bytes:
        backend = await self._start()
        if max_bytes is None:
            return await backend.read_file(path)
        return await backend.read_file(path, max_bytes=max_bytes)

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


async def hydrate_sandbox(
    sandbox: SandboxBackend,
    inputs: WorkspaceInputs,
) -> None:
    """Copy trusted application state and searchable references into one run."""
    started = time.perf_counter()
    files: dict[str, str | bytes] = {WORKSPACE_SCHEDULE: inputs.schedule_yaml}
    try:
        files[WORKSPACE_SOURCE_CONTEXT] = json.dumps(
            build_result_context(inputs.schedule_yaml), ensure_ascii=False, allow_nan=False
        )
    except Exception:
        # A draft may not compile. Its YAML remains available for direct inspection.
        logger.debug("Current schedule inspection context unavailable", exc_info=True)
    if inputs.pending_proposal is not None:
        files[WORKSPACE_PENDING_PROPOSAL] = inputs.pending_proposal.schedule_yaml
        files[WORKSPACE_PENDING_DIFF] = inputs.pending_proposal.diff
    for group, path in REFERENCE_SCHEMAS.items():
        reference = load_taiwan_holidays_reference() if group == "taiwan-holidays" else load_schedule_reference(group)
        if reference is None:  # pragma: no cover - constants are defined together
            raise ValueError(f"unknown schedule reference group: {group}")
        files[path] = reference
    for relative_path, reference in load_user_guide_references().items():
        files[f"{REFERENCE_USER_GUIDE}/{relative_path}"] = reference
    for destination, source in REFERENCE_ATTACHMENT_TOOLS.items():
        files[destination] = source.read_text(encoding="utf-8")
    files["/reference/tools/README.md"] = inspection_helper_catalog()
    for index, attachment in enumerate(inputs.attachments, start=1):
        files[attachment_path(attachment, index)] = attachment.data
    if inputs.optimizer_result is not None:
        files[WORKSPACE_OPTIMIZER_RESULT] = inputs.optimizer_result
        files[WORKSPACE_RESULT_CONTEXT] = (
            inputs.optimizer_context
            if inputs.optimizer_context is not None
            else json.dumps(
                build_result_context(inputs.schedule_yaml, workbook=inputs.optimizer_result),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        if inputs.pending_proposal is not None:
            files[WORKSPACE_PENDING_RESULT_CONTEXT] = json.dumps(
                build_result_context(inputs.pending_proposal.schedule_yaml), ensure_ascii=False, allow_nan=False
            )
    # One request, because hydration now precedes the first tool result rather than the run.
    await sandbox.write_files(files)
    logger.info(
        "sandbox hydrated sandbox_id=%s files=%s schedule_bytes=%s latency_seconds=%.3f",
        sandbox.sandbox_id,
        len(files),
        len(inputs.schedule_yaml.encode("utf-8")),
        time.perf_counter() - started,
    )


def attachment_path(attachment: SandboxAttachment, index: int) -> str:
    """Return a deterministic path below the fixed attachment directory, prefixed by the upload ID or position."""
    basename = attachment.filename.replace("\\", "/").rsplit("/", 1)[-1]
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    if not sanitized:
        sanitized = "attachment"
    return f"{WORKSPACE_ATTACHMENTS}/{attachment.id or f'{index:02d}'}-{sanitized[:120]}"


async def read_download(sandbox: SandboxBackend, max_download_bytes: int) -> bytes | None:
    """Capture and validate the optional generated ZIP before sandbox cleanup."""
    try:
        download = await sandbox.read_file(WORKSPACE_DOWNLOAD, max_bytes=max_download_bytes)
    except SandboxFileNotFoundError:
        return None
    except SandboxFileSizeError as exc:
        raise SandboxDownloadValidationError(str(exc)) from exc
    except SandboxError as exc:
        raise SandboxDownloadError(str(exc)) from exc
    try:
        await asyncio.to_thread(validate_download_zip, download, max_download_bytes)
    except ValueError as exc:
        raise SandboxDownloadValidationError(str(exc)) from exc
    return download


async def _read_candidate(sandbox: SandboxBackend, max_schedule_bytes: int) -> str:
    started = time.perf_counter()
    try:
        candidate = await sandbox.read_file(WORKSPACE_SCHEDULE)
    except SandboxFileNotFoundError as exc:
        # The model owns the working copy and can delete it, which is a failed
        # run rather than a sandbox failure.
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

    async def review_if_changed(self) -> tuple[AgentToolResult, str | None] | None:
        prefix = "Trusted schedule check after this command:"
        try:
            content = await self._sandbox.read_file(WORKSPACE_SCHEDULE)
        except SandboxFileNotFoundError:
            # Report the deletion to the model instead of failing the run, so it
            # can restore the working copy it removed.
            return (
                AgentToolResult(
                    f"{prefix}\nThe working copy {WORKSPACE_SCHEDULE} no longer exists. "
                    "Restore it before finishing this run.",
                    False,
                ),
                None,
            )
        if content == self._last_content:
            return None
        self._last_content = content
        if len(content) > self._max_bytes:
            return (
                AgentToolResult(
                    f"{prefix}\nThe candidate exceeds the {self._max_bytes}-byte schedule limit.",
                    False,
                ),
                None,
            )
        try:
            candidate = content.decode("utf-8")
        except UnicodeDecodeError:
            return (
                AgentToolResult(f"{prefix}\nThe candidate is not valid UTF-8.", False),
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
                AgentToolResult(
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
            AgentToolResult(f"{prefix}\n{guidance}{review.outcome.text}", review.outcome.ok),
            candidate if review.outcome.ok else None,
        )
