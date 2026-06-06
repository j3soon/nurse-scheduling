"""Tests for the real-scenario CLI wrapper."""

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

import sys

import pytest

from .real import run_schedule


def test_run_schedule_removes_temp_file_when_write_fails(tmp_path, monkeypatch):
    input_path = tmp_path / "input.yaml"
    input_path.write_text("apiVersion: alpha\n", encoding="utf-8")
    temp_path = tmp_path / "temporary.yaml"

    class FailingTemporaryFile:
        name = str(temp_path)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def write(self, content):
            temp_path.write_bytes(content)
            raise OSError("write failed")

    monkeypatch.setattr(sys, "argv", ["run_schedule.py", str(input_path)])
    monkeypatch.setattr(run_schedule.tempfile, "NamedTemporaryFile", lambda **kwargs: FailingTemporaryFile())

    with pytest.raises(OSError, match="write failed"):
        run_schedule.main()

    assert not temp_path.exists()
