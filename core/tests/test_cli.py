"""Unit tests for the CLI entrypoint."""

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
import sys

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import cli


def test_cli_missing_input_file_exits_with_error(tmp_path, monkeypatch, capsys):
    missing_file = str(tmp_path / "does-not-exist.yaml")
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", missing_file])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert f"Error: File '{missing_file}' not found" in out


def test_cli_rejects_prettify_for_csv_output(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")
    output_file = tmp_path / "output.csv"
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", str(input_file), str(output_file), "--prettify"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Error: Prettify mode is not supported for CSV files" in out


def test_cli_rejects_unsupported_output_extension(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")
    output_file = tmp_path / "output.txt"
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", str(input_file), str(output_file)])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Error: Unsupported output file extension '.txt'" in out


def test_cli_writes_csv_output_with_solver_and_timeout(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_content = b"fake input payload"
    input_file.write_bytes(input_content)
    output_file = tmp_path / "result.csv"

    seen = {}

    def fake_schedule(file_content, prettify, timeout, solver):
        seen["schedule_args"] = {
            "file_content": file_content,
            "prettify": prettify,
            "timeout": timeout,
            "solver": solver,
        }
        return "fake_df", {"solution": True}, 123, "OPTIMAL", {"styles": {}, "comments": {}}

    def fake_export_to_csv(df, buffer):
        seen["export_df"] = df
        buffer.write(b"csv-bytes")

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(cli.exporter, "export_to_csv", fake_export_to_csv)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nurse-scheduling",
            str(input_file),
            str(output_file),
            "--timeout",
            "7",
            "--solver",
            "pulp/cbc",
        ],
    )

    cli.main()

    assert seen["schedule_args"] == {
        "file_content": input_content,
        "prettify": False,
        "timeout": 7,
        "solver": "pulp/cbc",
    }
    assert seen["export_df"] == "fake_df"
    assert output_file.read_bytes() == b"csv-bytes"
    out = capsys.readouterr().out
    assert f"Results saved to {output_file}" in out
    assert "Score: 123" in out
    assert "Status: OPTIMAL" in out


def test_cli_no_solution_exits_zero(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")

    def fake_schedule(file_content, prettify, timeout, solver):
        return None, None, None, "INFEASIBLE", {}

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", str(input_file)])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "No solution found" in out


def test_cli_writes_xlsx_output(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")
    output_file = tmp_path / "result.xlsx"
    seen = {}

    def fake_schedule(file_content, prettify, timeout, solver):
        return "df", {}, 0, "OPTIMAL", {"styles": {(1, 1): {"backgroundColor": "#ffffff"}}, "comments": {}}

    def fake_export_to_excel(df, buffer, cell_export_info):
        seen["df"] = df
        seen["cell_export_info"] = cell_export_info
        buffer.write(b"xlsx-bytes")

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(cli.exporter, "export_to_excel", fake_export_to_excel)
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", str(input_file), str(output_file), "--prettify"])

    cli.main()

    assert seen["df"] == "df"
    assert seen["cell_export_info"] == {"styles": {(1, 1): {"backgroundColor": "#ffffff"}}, "comments": {}}
    assert output_file.read_bytes() == b"xlsx-bytes"
    out = capsys.readouterr().out
    assert f"Results saved to {output_file}" in out
    assert "Status: OPTIMAL" in out
