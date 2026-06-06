"""Run the scheduler CLI with real-test critical-request comments injected.

This helper always adds the critical-request comment formatting rules used by
the real-world smoke tests before invoking the normal production CLI in a
subprocess. All CLI behavior after YAML preprocessing comes from
``python -m nurse_scheduling.cli``.
"""

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

import subprocess
import sys
import tempfile
from pathlib import Path

CORE_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(CORE_ROOT))

try:
    from .schedule_real_helper import _add_critical_request_formatting_rules
except ImportError:
    from schedule_real_helper import _add_critical_request_formatting_rules


def _usage() -> str:
    return (
        "usage: run_schedule.py input_file_path [cli_args...]\n\n"
        "Runs python -m nurse_scheduling.cli after injecting the real-test "
        "critical-request comment formatting rules."
    )


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(_usage())
        return 0 if len(sys.argv) >= 2 else 2

    input_path = Path(sys.argv[1])
    if not input_path.is_file():
        print(f"Error: File '{input_path}' not found")
        return 1

    cli_args = sys.argv[2:]
    file_content = _add_critical_request_formatting_rules(input_path.read_bytes())

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="nurse-scheduling-real-", suffix=".yaml", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(file_content)

        completed_process = subprocess.run(
            [sys.executable, "-m", "nurse_scheduling.cli", str(temp_path), *cli_args],
            check=False,
        )
        return completed_process.returncode
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
