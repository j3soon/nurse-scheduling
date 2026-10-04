"""Linux command isolation and verified cleanup inside an E2B sandbox."""

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

import shlex

# E2B starts a login shell. Exec preserves its PID, which the SDK handle exposes.
# Subreaping keeps orphaned descendants discoverable while the command is alive.
ISOLATE_SOURCE = """import ctypes, os, sys
if os.getpgrp() != os.getpid():
    os.setsid()
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), "Cannot track command descendants")
os.execv("/bin/bash", ["bash", "-c", sys.argv[1]])
"""

# A successful cleanup proves no live member of the isolated group remains.
# Zombies cannot execute or mutate files. Escaped descendants require teardown.
STOP_GROUP_SOURCE = """import os, pathlib, signal, sys, time
pid = int(sys.argv[1])

def processes():
    found = {}
    for path in pathlib.Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            continue
        found[int(path.parent.name)] = (fields[0], int(fields[1]), int(fields[2]), fields[19])
    return found

initial = processes()
root = initial.get(pid)
if not root or root[0] in ("Z", "X") or root[2] != pid or os.getpgrp() == pid:
    sys.exit(1)
tracked = {pid}
while True:
    children = {child for child, state in initial.items() if state[1] in tracked}
    if children <= tracked:
        break
    tracked |= children
if any(initial[child][0] not in ("Z", "X") and initial[child][2] != pid for child in tracked):
    sys.exit(1)
deadline = time.monotonic() + 1
while True:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    current = processes()
    live_group = any(state[0] not in ("Z", "X") and state[2] == pid for state in current.values())
    live_tracked = any(child in current and current[child][3] == initial[child][3] and current[child][0] not in ("Z", "X") for child in tracked)
    if not live_group and not live_tracked:
        break
    if time.monotonic() >= deadline:
        sys.exit(1)
    time.sleep(0.02)
"""


def isolated_command(command: str) -> str:
    """Preserve literal shell text and the SDK PID while isolating its process group."""
    return f"exec python3 -c {shlex.quote(ISOLATE_SOURCE)} {shlex.quote(command)}"


def stop_command_group(pid: int) -> str:
    """Build a cleanup probe that succeeds only after verified group termination."""
    if pid <= 1:
        raise ValueError("Command PID must exceed 1")
    return f"python3 -c {shlex.quote(STOP_GROUP_SOURCE)} {pid}"
