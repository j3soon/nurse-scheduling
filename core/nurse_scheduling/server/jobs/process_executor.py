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

import ctypes
import logging
import math
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from multiprocessing.connection import Connection
from typing import Any

from ..config import (
    DEFAULT_CANCEL_GRACE_SECONDS,
    DEFAULT_TIMEOUT_GRACE_SECONDS,
)
from ..errors import OptimizationExecutionError
from .models import Job
from .runner import EventCallback, OptimizationRunner, RunOutput, StopCallback


server_logger = logging.getLogger("nurse_scheduling.server")
PROCESS_POLL_SECONDS = 0.05
"""Maximum delay for progress, controls, aborts, and watchdog checks."""
PR_SET_PDEATHSIG = 1
"""Linux prctl operation that configures a signal for parent process death."""


class OptimizationProcessAborted(Exception):
    """Internal signal that claim loss or server shutdown stopped execution."""


class OptimizationForcedCancellation(Exception):
    """Signal that cancellation required terminating the solver process."""


class ChildOptimizationError(RuntimeError):
    """Unexpected exception raised by the isolated optimization runner."""

    def __init__(self, exception_type: str, message: str, child_traceback: str):
        """Retain child diagnostics while keeping the public message concise."""
        super().__init__(f"{exception_type}: {message}")
        self.child_traceback = child_traceback


def _set_parent_death_signal(expected_parent_pid: int) -> None:
    """Ensure Linux kills the optimization child if its supervisor disappears."""
    if sys.platform != "linux":
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
    if os.getppid() != expected_parent_pid:
        os.kill(os.getpid(), signal.SIGKILL)


def _run_child(
    runner: OptimizationRunner,
    job: Job,
    input_bytes: bytes,
    connection: Connection,
    stop_event: Any,
    child_finished_event: Any,
    cooperative_stop_enabled: bool,
    expected_parent_pid: int,
) -> None:
    """Execute the runner and send events or its terminal message to the parent."""
    _set_parent_death_signal(expected_parent_pid)
    if os.name == "posix":
        os.setsid()

    def publish(event_type: str, data: dict[str, Any], score: int | None) -> None:
        connection.send(("event", event_type, data, score))

    should_stop = stop_event.is_set if cooperative_stop_enabled else None
    try:
        output = runner.run(
            job,
            input_bytes,
            event_callback=publish,
            should_stop=should_stop,
        )
        child_finished_event.set()
        connection.send(("output", output))
    except OptimizationExecutionError as error:
        child_finished_event.set()
        connection.send(("execution_error", error.code, str(error)))
    except BaseException as error:
        child_finished_event.set()
        connection.send(
            (
                "unexpected_error",
                type(error).__name__,
                str(error),
                traceback.format_exc(),
            )
        )
    finally:
        connection.close()


def _kill_process_tree_by_pid(process_id: int) -> None:
    """Forcibly terminate a process group or Windows process tree by PID."""
    if os.name == "posix":
        try:
            os.killpg(process_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _kill_process_tree(process: multiprocessing.Process) -> None:
    """Forcibly terminate a child and solver executables launched beneath it."""
    if not process.is_alive():
        return
    _kill_process_tree_by_pid(process.pid)
    if process.is_alive():
        process.kill()
    process.join(timeout=1)


def _guard_process_tree(
    connection: Connection,
    child_process_id: int,
    child_finished_event: Any,
) -> None:
    """Kill the solver process group if its supervising process disappears."""
    if os.name == "posix":
        os.setsid()
    try:
        try:
            connection.recv()
        except (EOFError, OSError):
            if not child_finished_event.is_set():
                _kill_process_tree_by_pid(child_process_id)
    finally:
        connection.close()


class ProcessOptimizationExecutor:
    """Supervise a spawned optimization process and enforce its hard deadline."""

    def __init__(
        self,
        *,
        timeout_grace_seconds: float = DEFAULT_TIMEOUT_GRACE_SECONDS,
        cancel_grace_seconds: float = DEFAULT_CANCEL_GRACE_SECONDS,
    ):
        """Configure forced-timeout and graceful-cancellation grace periods."""
        if not math.isfinite(timeout_grace_seconds) or timeout_grace_seconds <= 0:
            raise ValueError("timeout_grace_seconds must be positive")
        if not math.isfinite(cancel_grace_seconds) or cancel_grace_seconds <= 0:
            raise ValueError("cancel_grace_seconds must be positive")
        self._timeout_grace_seconds = timeout_grace_seconds
        self._cancel_grace_seconds = cancel_grace_seconds
        self._context = multiprocessing.get_context("spawn")

    def run(
        self,
        runner: OptimizationRunner,
        job: Job,
        input_bytes: bytes,
        *,
        event_callback: EventCallback,
        should_stop: StopCallback | None,
        should_cancel: StopCallback,
        graceful_cancel: bool,
        should_abort: StopCallback,
    ) -> RunOutput:
        """Run one job and enforce hard process deadlines.

        The timeout deadline starts when the child process starts. It includes
        the requested timeout and timeout grace period.

        Raises:
            OptimizationExecutionError: If execution fails or the watchdog fires.
            OptimizationForcedCancellation: If cancellation requires process termination.
            OptimizationProcessAborted: If shutdown or claim loss requires an immediate stop.
            ChildOptimizationError: If the child raises an unexpected exception.
        """
        receive_connection, send_connection = self._context.Pipe(duplex=False)
        stop_event = self._context.Event()
        child_finished_event = self._context.Event()
        process = self._context.Process(
            target=_run_child,
            args=(
                runner,
                job,
                input_bytes,
                send_connection,
                stop_event,
                child_finished_event,
                should_stop is not None or graceful_cancel,
                os.getpid(),
            ),
            name=f"optimization-job-{job.id}",
        )
        guard_process: multiprocessing.Process | None = None
        guard_send_connection: Connection | None = None
        stop_forwarded = False
        cancel_forwarded = False
        watchdog_fired = threading.Event()
        watchdog_timer: threading.Timer | None = None
        cancellation_started = threading.Event()
        cancellation_fired = threading.Event()
        cancellation_timer: threading.Timer | None = None
        process_stop_lock = threading.Lock()
        try:
            process.start()
        except BaseException:
            receive_connection.close()
            send_connection.close()
            raise
        send_connection.close()
        # The detached guard survives supervisor death long enough to kill the
        # optimization process group, including external solver descendants.
        guard_receive_connection, guard_send_connection = self._context.Pipe(duplex=False)
        guard_process = self._context.Process(
            target=_guard_process_tree,
            args=(
                guard_receive_connection,
                process.pid,
                child_finished_event,
            ),
            name=f"optimization-job-guard-{job.id}",
            daemon=True,
        )
        try:
            guard_process.start()
        except BaseException:
            guard_receive_connection.close()
            guard_send_connection.close()
            with process_stop_lock:
                _kill_process_tree(process)
            receive_connection.close()
            raise
        guard_receive_connection.close()
        process_started_at = time.monotonic()
        hard_timeout_seconds = job.request.timeout_seconds + self._timeout_grace_seconds

        def force_timeout() -> None:
            """Kill a child that has not returned by its hard deadline."""
            if child_finished_event.is_set() or cancellation_started.is_set():
                return
            watchdog_fired.set()
            with process_stop_lock:
                _kill_process_tree(process)

        def watchdog_error() -> OptimizationExecutionError:
            """Build the stable failure exposed for forced termination."""
            return OptimizationExecutionError(
                "timeout_forced",
                (
                    f"The optimization process did not return within the requested "
                    f"{job.request.timeout_seconds}-second timeout and "
                    f"{self._timeout_grace_seconds:g}-second timeout grace period. "
                    "The server terminated the process."
                ),
            )

        def force_cancel() -> None:
            """Kill a child that cannot complete cancellation gracefully."""
            if child_finished_event.is_set():
                return
            cancellation_fired.set()
            with process_stop_lock:
                _kill_process_tree(process)

        def forced_cancellation_error() -> OptimizationForcedCancellation:
            """Build the stable failure exposed for forced cancellation."""
            if graceful_cancel:
                message = (
                    f"The solver did not stop within the {self._cancel_grace_seconds:g}-second "
                    "cancellation grace period. The server terminated the solver process."
                )
            else:
                message = "The solver does not support graceful cancellation. The server terminated the solver process."
            return OptimizationForcedCancellation(message)

        try:
            watchdog_timer = threading.Timer(hard_timeout_seconds, force_timeout)
            watchdog_timer.daemon = True
            watchdog_timer.start()
            while True:
                if should_abort():
                    raise OptimizationProcessAborted
                if not cancel_forwarded and should_cancel():
                    cancel_forwarded = True
                    cancellation_started.set()
                    if watchdog_timer is not None:
                        watchdog_timer.cancel()
                    if graceful_cancel:
                        stop_event.set()
                        cancellation_timer = threading.Timer(
                            self._cancel_grace_seconds,
                            force_cancel,
                        )
                        cancellation_timer.daemon = True
                        cancellation_timer.start()
                    else:
                        force_cancel()
                if cancellation_fired.is_set():
                    raise forced_cancellation_error()
                if watchdog_fired.is_set():
                    raise watchdog_error()
                if should_stop is not None and not stop_forwarded and should_stop():
                    stop_event.set()
                    stop_forwarded = True

                if receive_connection.poll(PROCESS_POLL_SECONDS):
                    try:
                        message = receive_connection.recv()
                    except EOFError:
                        message = None
                    if message is not None:
                        message_type = message[0]
                        if message_type == "event":
                            _, event_type, data, score = message
                            event_callback(event_type, data, score)
                            continue
                        if message_type == "output":
                            process.join(timeout=1)
                            return message[1]
                        if message_type == "execution_error":
                            _, code, error_message = message
                            raise OptimizationExecutionError(code, error_message)
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

                hard_deadline = process_started_at + hard_timeout_seconds
                if time.monotonic() >= hard_deadline:
                    force_timeout()
                    if watchdog_fired.is_set():
                        raise watchdog_error()

                if not process.is_alive():
                    if cancellation_fired.is_set():
                        raise forced_cancellation_error()
                    if watchdog_fired.is_set():
                        raise watchdog_error()
                    if receive_connection.poll():
                        continue
                    raise ChildOptimizationError(
                        "ChildProcessExit",
                        f"Optimization process exited with code {process.exitcode}",
                        "",
                    )
        finally:
            if watchdog_timer is not None:
                watchdog_timer.cancel()
            if cancellation_timer is not None:
                cancellation_timer.cancel()
            with process_stop_lock:
                if process.is_alive():
                    _kill_process_tree(process)
            receive_connection.close()
            if guard_send_connection is not None:
                try:
                    guard_send_connection.send("stop")
                except (BrokenPipeError, EOFError, OSError):
                    pass
                guard_send_connection.close()
            if guard_process is not None:
                guard_process.join(timeout=1)
                if guard_process.is_alive():
                    guard_process.kill()
                    guard_process.join(timeout=1)
