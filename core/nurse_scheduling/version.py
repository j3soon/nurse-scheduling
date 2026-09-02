"""Resolve the application version for standalone processes."""

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

import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_VERSION_FILE = REPOSITORY_ROOT / ".app-version"


def get_app_version() -> str:
    """Return the generated build version or the current Git description."""
    try:
        generated_version = APP_VERSION_FILE.read_text(encoding="utf-8").strip()
        if generated_version:
            return generated_version
    except OSError:
        pass
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={REPOSITORY_ROOT}",
                "-C",
                str(REPOSITORY_ROOT),
                "describe",
                "--tags",
                "--always",
                "--dirty",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "v0.0.0-unknown"
