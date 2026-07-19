"""Prepare and forcibly clean isolated optimization process trees."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

# This module contains the operating-system-specific cleanup used by the
# otherwise platform-neutral process executor.
#
# Process topology:
#
#   server supervisor
#   ├── optimization child and its process group
#   │   └── external solver descendants
#   └── detached process-tree guard
#
# - `prepare_optimization_child` gives the optimization child its own POSIX
#   session and process group before the runner starts. On Linux it also asks
#   the kernel to kill the direct child when the expected supervisor dies. The
#   parent-PID check closes the race where the supervisor exits before prctl is
#   configured.
# - PuLP command-line backends such as CBC and GLPK launch external solver
#   executables beneath the optimization child. Forced cancellation must kill
#   that complete tree. OR-Tools executes inside the optimization child and
#   does not create a solver-process descendant.
# - `kill_process_tree` handles normal forced cleanup. POSIX sends SIGKILL to
#   the isolated process group. Windows asks taskkill to terminate the process
#   and its descendants. A direct process kill remains as a fallback.
# - `ProcessTreeGuard` is a separate daemon process that waits on a pipe owned
#   by the supervisor. The executor releases the optimization child's startup
#   gate only after this guard starts. Normal cleanup sets the shared completion
#   event and sends a stop message. Abrupt supervisor death closes the pipe, so
#   the guard kills the optimization process tree before exiting.
# - The guard creates its own POSIX session so process-group cleanup never
#   terminates the guard before it can finish its work. The executor also
#   watches the guard and aborts the optimization if the guard exits early.

import ctypes
import multiprocessing
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.context import BaseContext
from typing import Any


PR_SET_PDEATHSIG = 1
"""Linux prctl operation that configures a signal for parent process death."""


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


def prepare_optimization_child(expected_parent_pid: int) -> None:
    """Isolate an optimization child before it can launch solver descendants.

    PuLP command-line backends launch external solver processes, so forced
    cleanup must cover the complete process tree. OR-Tools runs inside the
    optimization child and does not require descendant-process cleanup.
    """
    _set_parent_death_signal(expected_parent_pid)
    if os.name == "posix":
        os.setsid()


def _kill_process_tree_by_pid(process_id: int) -> None:
    """Forcibly terminate a POSIX process group or Windows process tree."""
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


def kill_process_tree(process: multiprocessing.Process) -> None:
    """Forcibly terminate a child and any external solver descendants."""
    # Reap an exited direct child before signaling its group. Darwin returns
    # EPERM when a process group contains only an unreaped zombie leader.
    process.join(timeout=0)
    if process.pid is not None:
        _kill_process_tree_by_pid(process.pid)
    if process.is_alive():
        process.kill()
    process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)


def _guard_process_tree(
    connection: Connection,
    child_process_id: int,
    process_tree_cleaned_event: Any,
) -> None:
    """Kill the optimization process tree if its supervisor disappears."""
    if os.name == "posix":
        os.setsid()
    try:
        try:
            connection.recv()
        except (EOFError, OSError):
            if not process_tree_cleaned_event.is_set():
                _kill_process_tree_by_pid(child_process_id)
    finally:
        connection.close()


@dataclass
class ProcessTreeGuard:
    """Guard that survives abrupt supervisor death long enough to clean a tree."""

    process: multiprocessing.Process
    send_connection: Connection
    process_tree_cleaned_event: Any

    @property
    def sentinel(self) -> int:
        """Return the waitable handle that signals when the guard exits."""
        return self.process.sentinel

    @property
    def exitcode(self) -> int | None:
        """Return the guard process exit code when available."""
        return self.process.exitcode

    @classmethod
    def start(
        cls,
        context: BaseContext,
        child_process_id: int,
        *,
        name: str,
    ) -> "ProcessTreeGuard":
        """Start a detached guard for one optimization process tree."""
        process_tree_cleaned_event = context.Event()
        receive_connection, send_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_guard_process_tree,
            args=(
                receive_connection,
                child_process_id,
                process_tree_cleaned_event,
            ),
            name=name,
            daemon=True,
        )
        try:
            process.start()
        except BaseException:
            receive_connection.close()
            send_connection.close()
            raise
        receive_connection.close()
        return cls(
            process=process,
            send_connection=send_connection,
            process_tree_cleaned_event=process_tree_cleaned_event,
        )

    def close(self) -> None:
        """Mark cleanup complete and stop the detached guard."""
        self.process_tree_cleaned_event.set()
        try:
            self.send_connection.send("stop")
        except (BrokenPipeError, EOFError, OSError):
            pass
        self.send_connection.close()
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=1)
