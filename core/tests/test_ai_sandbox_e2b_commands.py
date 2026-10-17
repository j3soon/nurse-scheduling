"""Process-level checks for E2B command isolation and cleanup."""

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
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nurse_scheduling.ai.sandbox.e2b_commands import STOP_GROUP_SOURCE, isolated_command, stop_command_group

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="E2B command cleanup uses Linux /proc")


def test_isolation_preserves_literal_shell_arguments_and_normal_exit_status():
    command = "printf '%s\\n' 'literal $HOME `uname` and spaces'; exit 124"
    result = subprocess.run(
        ["bash", "-c", isolated_command(command)], capture_output=True, text=True, timeout=5, check=False
    )
    assert result.stdout == "literal $HOME `uname` and spaces\n"
    assert result.returncode == 124  # A normal exit 124 is not proof of a timeout.


def _live(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] not in {"Z", "X"}
    except (FileNotFoundError, ProcessLookupError):
        return False


@pytest.mark.parametrize("read_error", ["FileNotFoundError", "ProcessLookupError"])
def test_cleanup_ignores_disappearing_unrelated_process(read_error):
    read_errno = 2 if read_error == "FileNotFoundError" else 3
    parent = subprocess.Popen(
        ["bash", "-c", isolated_command("sleep 30")], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        deadline = time.monotonic() + 5
        while os.getpgid(parent.pid) != parent.pid and time.monotonic() < deadline:
            time.sleep(0.01)
        assert os.getpgid(parent.pid) == parent.pid
        # A proc entry can disappear after it was opened. Keep the real target
        # group available while injecting that read error for an unrelated PID.
        probe = (
            f"""import pathlib
previous_read = pathlib.Path.read_text
def read_stat(path, *args, **kwargs):
    if str(path) == "/proc/{unrelated.pid}/stat":
        raise {read_error}({read_errno}, "Process exited during read")
    return previous_read(path, *args, **kwargs)
pathlib.Path.read_text = read_stat
"""
            + STOP_GROUP_SOURCE
        )
        result = subprocess.run(
            [sys.executable, "-c", probe, str(parent.pid)], capture_output=True, timeout=3, check=False
        )
        assert result.returncode == 0, result.stderr.decode()
        parent.communicate(timeout=3)
        assert parent.returncode == -signal.SIGKILL
        assert unrelated.poll() is None
    finally:
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        parent.communicate(timeout=3)
        unrelated.terminate()
        unrelated.wait(timeout=3)


@pytest.mark.parametrize("escaped", [False, True], ids=["ordinary-child", "detached-orphan"])
def test_cleanup_stops_children_or_rejects_an_escaped_descendant(tmp_path, escaped):
    ready = tmp_path / "ready"
    late = tmp_path / "late"
    child_code = (
        "import os,pathlib,time; "
        + ("os.setsid(); " if escaped else "")
        + f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid())); "
        + f"time.sleep(30); pathlib.Path({str(late)!r}).write_text('late')"
    )
    launch = f"python3 -c {shlex.quote(child_code)}"
    # The escaped grandchild outlives its immediate parent. Subreaping must keep
    # it discoverable under the foreground shell before group cleanup begins.
    if escaped:
        launch = "python3 -c " + shlex.quote(
            "import subprocess; subprocess.Popen(" + repr(["python3", "-c", child_code]) + ")"
        )
    command = f"{launch} & sleep 30 & wait"
    parent = subprocess.Popen(["bash", "-c", isolated_command(command)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child_pid = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                candidate = int(ready.read_text())
                fields = Path(f"/proc/{candidate}/stat").read_text().rsplit(")", 1)[1].split()
                if int(fields[1]) == parent.pid:
                    child_pid = candidate
                    break
            except (FileNotFoundError, ProcessLookupError, ValueError):
                pass
            time.sleep(0.01)
        assert child_pid is not None
        assert _live(child_pid)
        result = subprocess.run(
            ["bash", "-c", stop_command_group(parent.pid)], capture_output=True, timeout=3, check=False
        )
        assert result.returncode == (1 if escaped else 0), result.stderr.decode()
        if not escaped:
            parent.communicate(timeout=3)
            assert not _live(child_pid)
        assert not late.exists()
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        parent.communicate(timeout=3)


def test_cleanup_skips_a_process_that_exits_while_its_status_is_read():
    # Linux raises ESRCH when a process exits between opening and reading its stat file.
    # The patch makes that happen for PID 1, which is never in the command group.
    exited_process = """import pathlib
read_text = pathlib.Path.read_text
def read_exited_stat(path, *args, **kwargs):
    if str(path) == "/proc/1/stat":
        raise ProcessLookupError(3, "No such process")
    return read_text(path, *args, **kwargs)
pathlib.Path.read_text = read_exited_stat
"""
    parent = subprocess.Popen(["bash", "-c", isolated_command("sleep 30 & wait")])
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if Path(f"/proc/{parent.pid}/stat").read_text().rsplit(")", 1)[1].split()[2] == str(parent.pid):
                break
            time.sleep(0.01)
        result = subprocess.run(
            ["python3", "-c", exited_process + STOP_GROUP_SOURCE, str(parent.pid)],
            capture_output=True,
            timeout=3,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()
        assert parent.wait(timeout=3) == -signal.SIGKILL
    finally:
        parent.kill()
        parent.wait(timeout=3)


def test_cleanup_refuses_a_pid_that_is_not_a_dedicated_command_group():
    # An ordinary child in pytest's process group must be rejected without signaling.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result = subprocess.run(["bash", "-c", stop_command_group(child.pid)], timeout=3, check=False)
        assert result.returncode == 1
        assert child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=3)
