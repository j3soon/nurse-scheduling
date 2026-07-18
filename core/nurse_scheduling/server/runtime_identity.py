"""Derive opaque identities for one backend server launch."""

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

import hashlib
import os
import socket
from multiprocessing import parent_process
from pathlib import Path


def _process_start_marker(process_id: int) -> str:
    """Return the Linux start-time marker for one process when available."""
    try:
        stat = Path(f"/proc/{process_id}/stat").read_text(encoding="utf-8")
        fields = stat.rsplit(")", maxsplit=1)[1].split()
        return fields[19]
    except (IndexError, OSError):
        return "unknown"


def _boot_marker() -> str:
    """Return a host boot marker when the runtime exposes one."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def get_deployment_id() -> str:
    """Derive one opaque identity shared by workers from the same server launch."""
    supervisor = parent_process()
    launch_process_id = supervisor.pid if supervisor is not None else os.getpid()
    seed = ":".join(
        (
            socket.gethostname(),
            _boot_marker(),
            str(launch_process_id),
            _process_start_marker(launch_process_id),
        )
    )
    return f"deployment-{hashlib.sha256(seed.encode()).hexdigest()[:20]}"
