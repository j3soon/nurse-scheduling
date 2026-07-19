"""Tests for isolated optimization process supervision."""

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

# This test is mostly AI generated.

import ctypes
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nurse_scheduling.server.jobs import process_tree
from nurse_scheduling.server.jobs.models import Job, JobRequest, JobState
from nurse_scheduling.server.jobs.process_executor import (
    ChildOptimizationError,
    ProcessControl,
    ProcessStatus,
    run_optimization_process,
)


class DescendantHangingRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
        )
        event_callback(
            "proof.processes",
            {
                "wrapper_pid": os.getpid(),
                "descendant_pid": descendant.pid,
            },
            None,
        )
        while True:
            time.sleep(1)


class ChildPidHangingRunner:
    def run(self, job, input_bytes, *, event_callback, should_stop):
        event_callback("proof.child", {"optimization_pid": os.getpid()}, None)
        while True:
            time.sleep(1)


class DirectReportingDescendantHangingRunner:
    def __init__(self, result_connection, started_event=None):
        self.result_connection = result_connection
        self.started_event = started_event

    def run(self, job, input_bytes, *, event_callback, should_stop):
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
        )
        self.result_connection.send(
            {
                "wrapper_pid": os.getpid(),
                "descendant_pid": descendant.pid,
            }
        )
        if self.started_event is not None:
            self.started_event.set()
        while True:
            time.sleep(1)


def _job(job_id: str) -> Job:
    return Job(
        id=job_id,
        state=JobState.RUNNING,
        request=JobRequest(
            input_name="input.yaml",
            client_id="client",
            solver="pulp/cbc",
            prettify=False,
            timeout_seconds=60,
        ),
        created_at=datetime.now(timezone.utc),
    )


def _linux_process_state(process_id: int) -> str:
    try:
        return Path(f"/proc/{process_id}/stat").read_text(encoding="utf-8").split()[2]
    except FileNotFoundError:
        return "missing"


def _linux_process_is_active(process_id: int) -> bool:
    return _linux_process_state(process_id) not in {"missing", "X", "Z"}


def _wait_for_linux_process_exit(process_id: int, timeout_seconds: float = 3) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _linux_process_is_active(process_id):
            return True
        time.sleep(0.02)
    return not _linux_process_is_active(process_id)


def _kill_and_reap_linux_process(process_id: int) -> None:
    try:
        os.kill(process_id, signal.SIGKILL)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            reaped_id, _status = os.waitpid(process_id, os.WNOHANG)
        except ChildProcessError:
            if not _linux_process_is_active(process_id):
                return
        else:
            if reaped_id == process_id:
                return
        time.sleep(0.02)
    raise RuntimeError(f"Failed to reap proof process {process_id}")


def _enable_linux_child_subreaper() -> None:
    pr_set_child_subreaper = 36
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(pr_set_child_subreaper, 1, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _parent_death_supervisor(result_connection) -> None:
    def publish(_event_type, data, _score):
        result_connection.send(data)

    run_optimization_process(
        ChildPidHangingRunner(),
        _job("job_parent_death"),
        b"apiVersion: alpha\n",
        event_callback=publish,
        control=lambda: None,
        hard_timeout_seconds=61,
        finish_now_enabled=False,
    )


def _delayed_guard_start_supervisor(
    phase_connection,
    runner_connection,
    runner_started_event,
) -> None:
    def delayed_start(cls, context, child_process_id, *, name):
        descendant_started = runner_started_event.wait(timeout=2)
        phase_connection.send(
            {
                "optimization_pid": child_process_id,
                "descendant_started_before_guard": descendant_started,
            }
        )
        time.sleep(300)

    process_tree.ProcessTreeGuard.start = classmethod(delayed_start)
    run_optimization_process(
        DirectReportingDescendantHangingRunner(
            runner_connection,
            runner_started_event,
        ),
        _job("job_delayed_guard_start"),
        b"apiVersion: alpha\n",
        event_callback=lambda _event_type, _data, _score: None,
        control=lambda: None,
        hard_timeout_seconds=61,
        finish_now_enabled=False,
    )


def _guard_death_supervisor(
    guard_connection,
    runner_connection,
    outcome_connection,
) -> None:
    original_start = process_tree.ProcessTreeGuard.start

    def reporting_start(cls, context, child_process_id, *, name):
        guard = original_start(context, child_process_id, name=name)
        guard_connection.send({"guard_pid": guard.process.pid})
        return guard

    process_tree.ProcessTreeGuard.start = classmethod(reporting_start)
    try:
        run_optimization_process(
            DirectReportingDescendantHangingRunner(runner_connection),
            _job("job_guard_death"),
            b"apiVersion: alpha\n",
            event_callback=lambda _event_type, _data, _score: None,
            control=lambda: None,
            hard_timeout_seconds=61,
            finish_now_enabled=False,
        )
    except BaseException as error:
        outcome_connection.send(
            {
                "exception_type": type(error).__name__,
                "message": str(error),
            }
        )
    finally:
        guard_connection.close()
        runner_connection.close()
        outcome_connection.close()


def _probe_cancelled_descendant_cleanup() -> dict:
    process_ids: dict[str, int] = {}
    descendant_pid: int | None = None

    def publish(_event_type, data, _score):
        nonlocal descendant_pid
        process_ids.update(data)
        descendant_pid = process_ids.get("descendant_pid", descendant_pid)

    try:
        result = run_optimization_process(
            DescendantHangingRunner(),
            _job("job_descendant_cancel"),
            b"apiVersion: alpha\n",
            event_callback=publish,
            control=lambda: ProcessControl.CANCEL if process_ids else None,
            hard_timeout_seconds=61,
            finish_now_enabled=False,
        )
        wrapper_pid = process_ids["wrapper_pid"]
        if descendant_pid is None:
            raise RuntimeError("Optimization child did not report its descendant PID")
        descendant_exited = _wait_for_linux_process_exit(descendant_pid)
        return {
            "executor_status": result.status.value,
            "wrapper_state": _linux_process_state(wrapper_pid),
            "descendant_state": _linux_process_state(descendant_pid),
            "descendant_still_active": not descendant_exited,
        }
    finally:
        if descendant_pid is not None:
            _kill_and_reap_linux_process(descendant_pid)


def _probe_parent_death_cleanup() -> dict:
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    supervisor = context.Process(target=_parent_death_supervisor, args=(send_connection,))
    optimization_pid = None
    supervisor.start()
    send_connection.close()
    try:
        if not receive_connection.poll(10):
            raise RuntimeError("Optimization child did not report its PID")
        optimization_pid = receive_connection.recv()["optimization_pid"]
        supervisor.kill()
        supervisor.join(timeout=3)
        optimization_exited = _wait_for_linux_process_exit(optimization_pid)
        return {
            "supervisor_exit_code": supervisor.exitcode,
            "optimization_state": _linux_process_state(optimization_pid),
            "optimization_still_active": not optimization_exited,
        }
    finally:
        receive_connection.close()
        if supervisor.is_alive():
            supervisor.kill()
            supervisor.join(timeout=3)
        if optimization_pid is not None:
            _kill_and_reap_linux_process(optimization_pid)


def _probe_delayed_guard_start_cleanup() -> dict:
    context = multiprocessing.get_context("spawn")
    phase_receive, phase_send = context.Pipe(duplex=False)
    runner_receive, runner_send = context.Pipe(duplex=False)
    runner_started_event = context.Event()
    supervisor = context.Process(
        target=_delayed_guard_start_supervisor,
        args=(phase_send, runner_send, runner_started_event),
    )
    optimization_pid = None
    descendant_pid = None
    supervisor.start()
    phase_send.close()
    runner_send.close()
    try:
        if not phase_receive.poll(10):
            raise RuntimeError("Delayed guard start was not reached")
        phase = phase_receive.recv()
        optimization_pid = phase["optimization_pid"]
        if phase["descendant_started_before_guard"]:
            if not runner_receive.poll(3):
                raise RuntimeError("Started descendant did not report its PID")
            descendant_pid = runner_receive.recv()["descendant_pid"]
        supervisor.kill()
        supervisor.join(timeout=3)
        optimization_exited = _wait_for_linux_process_exit(optimization_pid)
        descendant_exited = _wait_for_linux_process_exit(descendant_pid) if descendant_pid is not None else True
        return {
            **phase,
            "supervisor_exit_code": supervisor.exitcode,
            "optimization_still_active": not optimization_exited,
            "descendant_pid": descendant_pid,
            "descendant_still_active": not descendant_exited,
        }
    finally:
        phase_receive.close()
        runner_receive.close()
        if supervisor.is_alive():
            supervisor.kill()
            supervisor.join(timeout=3)
        if optimization_pid is not None:
            _kill_and_reap_linux_process(optimization_pid)
        if descendant_pid is not None:
            _kill_and_reap_linux_process(descendant_pid)


def _probe_guard_death_cleanup() -> dict:
    context = multiprocessing.get_context("spawn")
    guard_receive, guard_send = context.Pipe(duplex=False)
    runner_receive, runner_send = context.Pipe(duplex=False)
    outcome_receive, outcome_send = context.Pipe(duplex=False)
    supervisor = context.Process(
        target=_guard_death_supervisor,
        args=(guard_send, runner_send, outcome_send),
    )
    wrapper_pid = None
    descendant_pid = None
    guard_pid = None
    supervisor.start()
    guard_send.close()
    runner_send.close()
    outcome_send.close()
    try:
        if not guard_receive.poll(10):
            raise RuntimeError("Process-tree guard did not report its PID")
        guard_pid = guard_receive.recv()["guard_pid"]
        if not runner_receive.poll(10):
            raise RuntimeError("Optimization runner did not report its process IDs")
        process_ids = runner_receive.recv()
        wrapper_pid = process_ids["wrapper_pid"]
        descendant_pid = process_ids["descendant_pid"]

        os.kill(guard_pid, signal.SIGKILL)
        outcome = outcome_receive.recv() if outcome_receive.poll(3) else None
        wrapper_exited = _wait_for_linux_process_exit(wrapper_pid)
        descendant_exited = _wait_for_linux_process_exit(descendant_pid)
        if outcome is not None:
            supervisor.join(timeout=3)
        return {
            "outcome": outcome,
            "supervisor_still_active": supervisor.is_alive(),
            "wrapper_still_active": not wrapper_exited,
            "descendant_still_active": not descendant_exited,
        }
    finally:
        guard_receive.close()
        runner_receive.close()
        outcome_receive.close()
        if guard_pid is not None:
            try:
                os.kill(guard_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if supervisor.is_alive():
            supervisor.kill()
        supervisor.join(timeout=3)
        if wrapper_pid is not None:
            _kill_and_reap_linux_process(wrapper_pid)
        if descendant_pid is not None:
            _kill_and_reap_linux_process(descendant_pid)


def _execute_process_cleanup_probe(name: str) -> dict:
    _enable_linux_child_subreaper()
    if name == "cancelled-descendant":
        return _probe_cancelled_descendant_cleanup()
    if name == "parent-death":
        return _probe_parent_death_cleanup()
    if name == "delayed-guard-start":
        return _probe_delayed_guard_start_cleanup()
    if name == "guard-death":
        return _probe_guard_death_cleanup()
    raise ValueError(f"Unknown process cleanup probe: {name}")


def _run_process_cleanup_probe(name: str) -> dict:
    script = (
        "import json; "
        "from tests.test_process_executor import _execute_process_cleanup_probe; "
        f"print(json.dumps(_execute_process_cleanup_probe({name!r})))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


# Cancellation cleanup topology:
#
#   probe and executor
#   └── optimization wrapper
#       └── simulated PuLP command-line solver
#
# The runner reports both child PIDs before cancellation is requested. The
# executor must remove the wrapper and its solver descendant before returning.
@pytest.mark.skipif(sys.platform != "linux", reason="Linux process-tree verification")
def test_cancellation_terminates_solver_descendants():
    proof = _run_process_cleanup_probe("cancelled-descendant")

    assert proof["executor_status"] == ProcessStatus.CANCELLED.value
    assert proof["wrapper_state"] == "missing"
    assert not proof["descendant_still_active"], proof


# Abrupt supervisor-death topology:
#
#   probe acting as a child subreaper
#   └── supervisor
#       ├── optimization child
#       └── process-tree guard
#
# SIGKILL bypasses supervisor cleanup. The child parent-death signal and guard
# must still terminate the optimization child.
@pytest.mark.skipif(sys.platform != "linux", reason="Linux parent-death verification")
def test_supervisor_death_terminates_optimization_child():
    proof = _run_process_cleanup_probe("parent-death")

    assert proof["supervisor_exit_code"] == -signal.SIGKILL
    assert not proof["optimization_still_active"], proof


# Guard-start race topology:
#
#   probe
#   └── supervisor blocked while starting the guard
#       └── optimization child waiting at its startup gate
#
# The injected guard start never completes. Killing the supervisor must close
# the startup gate before the runner can launch an external solver descendant.
@pytest.mark.skipif(sys.platform != "linux", reason="Linux guard-start verification")
def test_runner_waits_for_process_tree_guard_before_starting():
    proof = _run_process_cleanup_probe("delayed-guard-start")

    assert proof["supervisor_exit_code"] == -signal.SIGKILL
    assert not proof["optimization_still_active"], proof
    assert not proof["descendant_started_before_guard"], proof
    assert not proof["descendant_still_active"], proof


# Unexpected guard-death topology:
#
#   supervisor
#   ├── optimization wrapper
#   │   └── simulated PuLP command-line solver
#   └── process-tree guard killed by the probe
#
# The supervisor must detect the guard sentinel, report a supervision error,
# and terminate the wrapper and solver descendant.
@pytest.mark.skipif(sys.platform != "linux", reason="Linux guard-death verification")
def test_guard_death_aborts_optimization_process_tree():
    proof = _run_process_cleanup_probe("guard-death")

    assert proof["outcome"] is not None, proof
    assert proof["outcome"]["exception_type"] == ChildOptimizationError.__name__
    assert "ProcessTreeGuardExit" in proof["outcome"]["message"]
    assert not proof["supervisor_still_active"], proof
    assert not proof["wrapper_still_active"], proof
    assert not proof["descendant_still_active"], proof
