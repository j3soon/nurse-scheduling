"""Run one optimization runner in a supervised child process."""

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

# Known cleanup limits and potential future hardening:
#
# - A POSIX descendant that creates a new session or process group escapes the
#   managed process group. Current supported solvers do not do this.
# - Simultaneous supervisor and guard loss can leave an external solver alive
#   before either cleanup owner responds.
# - A failed Windows taskkill leaves only the direct-child kill fallback.
# - SIGKILL cannot remove a process in uninterruptible kernel sleep until its
#   kernel operation returns.
# - Forced group termination can leave dead descendants as zombies when the
#   container's PID 1 does not reap them.
#
# Linux cgroups, Windows Job Objects, and an init reaper could close these gaps.
# They are intentionally deferred because the active-process cases are unlikely
# with the current solvers.

import logging
import multiprocessing
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from multiprocessing.connection import Connection, wait
from typing import Any

from .models import Job, JobFailure
from . import process_tree
from .runner import EventCallback, OptimizationRunner, RunOutput


server_logger = logging.getLogger("nurse_scheduling.server")
PROCESS_POLL_SECONDS = 0.05
"""Maximum delay for progress, controls, aborts, and watchdog checks."""


class ProcessControl(str, Enum):
    """Control requested by the worker while optimization is running."""

    FINISH = "finish"
    CANCEL = "cancel"
    ABORT = "abort"


class ProcessStatus(str, Enum):
    """Normal terminal status of a supervised optimization process."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTED = "aborted"


@dataclass(frozen=True)
class ProcessResult:
    """Terminal process status and its output or expected failure."""

    status: ProcessStatus
    output: RunOutput | None = None
    failure: JobFailure | None = None


ControlCallback = Callable[[], ProcessControl | None]


class ChildOptimizationError(RuntimeError):
    """Unexpected exception raised by the isolated optimization runner."""

    def __init__(self, exception_type: str, message: str, child_traceback: str):
        """Retain child diagnostics while keeping the public message concise."""
        super().__init__(f"{exception_type}: {message}")
        self.child_traceback = child_traceback


def _run_child(
    runner: OptimizationRunner,
    job: Job,
    input_bytes: bytes,
    connection: Connection,
    start_connection: Connection,
    finish_now_event: Any,
    finish_now_enabled: bool,
    expected_parent_pid: int,
) -> None:
    """Execute the runner and send events or its terminal message to the parent."""
    # Isolate the child first, then wait until the supervisor has installed its
    # guard. This prevents a PuLP solver descendant from starting during the
    # interval where abrupt supervisor death could leave it unprotected.
    process_tree.prepare_optimization_child(expected_parent_pid)
    try:
        start_connection.recv()
    except (EOFError, OSError):
        return
    finally:
        start_connection.close()

    def publish(event_type: str, data: dict[str, Any], score: int | None) -> None:
        connection.send(("event", event_type, data, score))

    try:
        try:
            result = runner.run(
                job,
                input_bytes,
                event_callback=publish,
                should_stop=finish_now_event.is_set if finish_now_enabled else None,
            )
            message = ("result", result)
        except BaseException as error:
            message = (
                "unexpected_error",
                type(error).__name__,
                str(error),
                traceback.format_exc(),
            )
        connection.send(message)
    finally:
        connection.close()


def run_optimization_process(
    runner: OptimizationRunner,
    job: Job,
    input_bytes: bytes,
    *,
    event_callback: EventCallback,
    control: ControlCallback,
    hard_timeout_seconds: float,
    finish_now_enabled: bool,
) -> ProcessResult:
    """Run one directly supervised child until it returns or must be stopped.

    The finish-now control alone sets the cooperative solver event. Cancel and
    abort both terminate the process tree immediately and return distinct
    statuses.

    The process-tree guard provides forced cleanup of external solver
    descendants.

    Raises:
        ChildOptimizationError: If the child raises or exits unexpectedly.
    """
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    # The child owns the receive end. Closing the supervisor's send end before
    # release makes the child exit without running the solver.
    start_receive_connection, start_send_connection = context.Pipe(duplex=False)
    finish_now_event = context.Event()
    process = context.Process(
        target=_run_child,
        args=(
            runner,
            job,
            input_bytes,
            send_connection,
            start_receive_connection,
            finish_now_event,
            finish_now_enabled,
            multiprocessing.current_process().pid,
        ),
        name=f"optimization-job-{job.id}",
    )
    process_tree_guard: process_tree.ProcessTreeGuard | None = None
    try:
        process.start()
    except BaseException:
        receive_connection.close()
        send_connection.close()
        start_receive_connection.close()
        start_send_connection.close()
        raise
    send_connection.close()
    start_receive_connection.close()
    assert process.pid is not None
    try:
        # The child is alive but blocked at its startup gate. Release it only
        # after the detached guard can clean its complete process tree.
        process_tree_guard = process_tree.ProcessTreeGuard.start(
            context,
            process.pid,
            name=f"optimization-job-guard-{job.id}",
        )
        start_send_connection.send("start")
    except BaseException:
        start_send_connection.close()
        process_tree.kill_process_tree(process)
        receive_connection.close()
        if process_tree_guard is not None:
            process_tree_guard.close()
        raise
    start_send_connection.close()
    hard_deadline = time.monotonic() + hard_timeout_seconds
    timeout_grace_seconds = hard_timeout_seconds - job.request.timeout_seconds

    try:
        while True:
            requested_control = control()
            if requested_control is ProcessControl.FINISH:
                if not finish_now_enabled:
                    raise RuntimeError("Finish-now was requested for an unsupported solver")
                finish_now_event.set()
            elif requested_control is ProcessControl.CANCEL:
                return ProcessResult(status=ProcessStatus.CANCELLED)
            elif requested_control is ProcessControl.ABORT:
                return ProcessResult(status=ProcessStatus.ABORTED)
            elif requested_control is not None:
                raise RuntimeError(f"Unknown optimization process control: {requested_control}")

            remaining_seconds = hard_deadline - time.monotonic()
            if remaining_seconds <= 0:
                return ProcessResult(
                    status=ProcessStatus.FAILED,
                    failure=JobFailure(
                        code="process_timeout",
                        message=(
                            "The optimization process did not return within the requested "
                            f"{job.request.timeout_seconds:g}-second timeout and "
                            f"{timeout_grace_seconds:g}-second timeout grace period. "
                            "The server terminated the process."
                        ),
                    ),
                )

            ready = wait(
                [
                    receive_connection,
                    process.sentinel,
                    process_tree_guard.sentinel,
                ],
                timeout=min(PROCESS_POLL_SECONDS, remaining_seconds),
            )
            # Continuing without the guard would allow an abrupt supervisor
            # death to orphan an external PuLP solver process.
            if process_tree_guard.sentinel in ready:
                raise ChildOptimizationError(
                    "ProcessTreeGuardExit",
                    (f"Optimization process-tree guard exited unexpectedly with code {process_tree_guard.exitcode}"),
                    "",
                )
            if receive_connection in ready:
                try:
                    message = receive_connection.recv()
                except EOFError:
                    raise ChildOptimizationError(
                        "ChildProcessCommunicationError",
                        (
                            "Optimization process closed its result channel without "
                            f"a terminal message. Exit code: {process.exitcode}"
                        ),
                        "",
                    ) from None
                message_type = message[0]
                if message_type == "event":
                    _, event_type, data, score = message
                    event_callback(event_type, data, score)
                    continue
                if message_type == "result":
                    result = message[1]
                    if isinstance(result, RunOutput):
                        return ProcessResult(status=ProcessStatus.COMPLETED, output=result)
                    if isinstance(result, JobFailure):
                        return ProcessResult(status=ProcessStatus.FAILED, failure=result)
                    raise RuntimeError(f"Unknown optimization runner result: {type(result).__name__}")
                if message_type == "unexpected_error":
                    _, exception_type, error_message, child_traceback = message
                    server_logger.error(
                        "[server:worker-child] failed job_id=%s exception_type=%s\n%s",
                        job.id,
                        exception_type,
                        child_traceback,
                    )
                    raise ChildOptimizationError(exception_type, error_message, child_traceback)
                raise RuntimeError(f"Unknown optimization child message: {message_type}")

            if process.sentinel in ready:
                if receive_connection.poll():
                    continue
                raise ChildOptimizationError(
                    "ChildProcessExit",
                    f"Optimization process exited with code {process.exitcode}",
                    "",
                )
    finally:
        try:
            # Stop the optimization tree before marking guard cleanup complete.
            # This ordering keeps abrupt supervisor death covered until the tree
            # no longer needs protection.
            process_tree.kill_process_tree(process)
        finally:
            receive_connection.close()
            if process_tree_guard is not None:
                process_tree_guard.close()
