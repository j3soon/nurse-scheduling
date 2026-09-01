"""Tests for the schema CLI installed in the AI sandbox image."""

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

from nurse_scheduling.ai.sandbox_agent import _schedule_reference

NSCTL = Path(__file__).parents[2] / "docker" / "e2b" / "nsctl"


def _run(schema_file: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(NSCTL), "--schema-file", str(schema_file), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_schema_commands_read_the_hydrated_reference(tmp_path: Path):
    schema_file = tmp_path / "schedule-schema.md"
    schema_file.write_text(_schedule_reference(), encoding="utf-8")

    overview = _run(schema_file, "schema")
    listed = _run(schema_file, "schema", "list")
    shown = _run(schema_file, "schema", "show", "preferences.shift count")
    searched = _run(schema_file, "schema", "search", "requiredNumPeople")

    assert overview.returncode == 0
    assert "Frontend-editable schedule.yaml schema" in overview.stdout
    assert listed.returncode == 0
    assert "preferences.shift count" in listed.stdout.splitlines()
    assert shown.returncode == 0
    assert shown.stdout.startswith("Path: preferences.shift count\n")
    assert "expression" in shown.stdout
    assert searched.returncode == 0
    assert "preferences.shift type requirement" in searched.stdout.splitlines()


def test_schema_show_reports_an_unknown_path(tmp_path: Path):
    schema_file = tmp_path / "schedule-schema.md"
    schema_file.write_text(_schedule_reference(), encoding="utf-8")

    result = _run(schema_file, "schema", "show", "shift count")

    assert result.returncode != 0
    assert "unknown schema path" in result.stderr
    assert "preferences.shift count" in result.stderr
