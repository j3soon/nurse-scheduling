"""Tests for the MODA Taiwan holiday parser helper."""

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
from pathlib import Path


def test_parse_script_output_matches_taiwan_holidays_ts_entries():
    script_dir = Path(__file__).resolve().parent
    parse_script = script_dir / "parse.py"
    taiwan_holidays_ts = script_dir.parent.parent / "web-frontend" / "src" / "utils" / "taiwanHolidays.ts"

    result = subprocess.run(
        [sys.executable, str(parse_script)],
        cwd=script_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    output_lines = [line for line in result.stdout.splitlines() if line.strip()]
    taiwan_holidays_source = taiwan_holidays_ts.read_text(encoding="utf-8")

    assert output_lines
    for line in output_lines:
        assert line in taiwan_holidays_source
