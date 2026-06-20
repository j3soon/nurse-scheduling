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
import json
from pathlib import Path

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import cli
from nurse_scheduling.solver_interface import SolverProgress


def test_cli_version_prints_git_version(monkeypatch, capsys):
    seen = {}

    def fake_check_output(cmd, stderr, text):
        seen["cmd"] = cmd
        seen["stderr"] = stderr
        seen["text"] = text
        return "v1.2.3-dirty\n"

    def fail_schedule(*args, **kwargs):
        raise AssertionError("schedule should not run for --version")

    monkeypatch.setattr(cli.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(cli.scheduler, "schedule", fail_schedule)
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", "--version"])

    cli.main()

    repo_root = Path(cli.__file__).resolve().parents[2]
    assert capsys.readouterr().out == "nurse-scheduling v1.2.3-dirty\n"
    assert seen["cmd"][:5] == [
        "git",
        "-c",
        f"safe.directory={repo_root}",
        "-C",
        str(repo_root),
    ]
    assert seen["cmd"][5:] == ["describe", "--tags", "--always", "--dirty"]
    assert seen["text"] is True


def test_cli_version_falls_back_when_git_version_is_unavailable(monkeypatch, capsys):
    def raise_git_error(*args, **kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(cli.subprocess, "check_output", raise_git_error)
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", "--version"])

    cli.main()

    assert capsys.readouterr().out == "nurse-scheduling v0.0.0-unknown\n"


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

    def fake_schedule(file_content, prettify, timeout, solver, progress_callback, model_build_stats_callback):
        seen["schedule_args"] = {
            "file_content": file_content,
            "prettify": prettify,
            "timeout": timeout,
            "solver": solver,
            "progress_callback": progress_callback,
            "model_build_stats_callback": model_build_stats_callback,
        }
        return "fake_df", {"solution": True}, 123, "OPTIMAL", {"styles": {}, "comments": {}}

    def fake_export_to_csv(df, buffer):
        seen["export_df"] = df
        buffer.write(b"csv-bytes")

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(cli.exporter, "export_to_csv", fake_export_to_csv)
    monkeypatch.setattr(cli, "_get_app_version", lambda: "v9.8.7-test")
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
        "progress_callback": seen["schedule_args"]["progress_callback"],
        "model_build_stats_callback": None,
    }
    assert callable(seen["schedule_args"]["progress_callback"])
    assert seen["export_df"] == "fake_df"
    assert output_file.read_bytes() == b"csv-bytes"
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "nurse-scheduling v9.8.7-test"
    assert f"Results saved to {output_file}" in out
    assert "Score: 123" in out
    assert "Status: OPTIMAL" in out


def test_cli_writes_progress_jsonl_output(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_bytes(b"fake input payload")
    progress_file = tmp_path / "progress.jsonl"

    def fake_schedule(file_content, prettify, timeout, solver, progress_callback, model_build_stats_callback):
        progress_callback(
            SolverProgress(
                source="ortools/cp-sat:solution-callback",
                currentBestScore=12,
                elapsedSeconds=0.25,
                solutionIndex=1,
                cell_export_info={"comments": {(1, 2): ["a", "b"]}, "styles": {}},
            )
        )
        return "fake_df", {"solution": True}, 12, "OPTIMAL", {"comments": {(1, 2): ["a", "b", "c"]}, "styles": {}}

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nurse-scheduling",
            str(input_file),
            "--prettify",
            "--progress-output",
            str(progress_file),
        ],
    )

    cli.main()

    progress_events = [json.loads(line) for line in progress_file.read_text(encoding="utf-8").splitlines()]
    assert progress_events[0] == {
        "currentBestScore": 12,
        "elapsedSeconds": 0.25,
        "commentCount": 2,
        "solutionIndex": 1,
        "source": "ortools/cp-sat:solution-callback",
    }
    assert progress_events[1]["source"] == "cli:final-result"
    assert progress_events[1]["currentBestScore"] == 12
    assert progress_events[1]["commentCount"] == 3
    assert progress_events[1]["solutionIndex"] is None
    assert progress_events[1]["elapsedSeconds"] >= 0
    assert "comments=3" in capsys.readouterr().out


def test_cli_rejects_progress_jsonl_without_prettify(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_bytes(b"fake input payload")
    progress_file = tmp_path / "progress.jsonl"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nurse-scheduling",
            str(input_file),
            "--progress-output",
            str(progress_file),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    assert "Error: --progress-output requires --prettify" in capsys.readouterr().out
    assert not progress_file.exists()


def test_cli_no_solution_exits_zero(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")

    def fake_schedule(file_content, prettify, timeout, solver, progress_callback, model_build_stats_callback):
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

    def fake_schedule(file_content, prettify, timeout, solver, progress_callback, model_build_stats_callback):
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


def test_cli_prints_final_comments_from_export_comments(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")

    def fake_schedule(file_content, prettify, timeout, solver, progress_callback, model_build_stats_callback):
        return "df", {}, 0, "OPTIMAL", {"styles": {}, "comments": {(1, 2): ["first", "second"], (3, 4): ["third"]}}

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", str(input_file)])

    cli.main()

    assert "Comments: 3" in capsys.readouterr().out


def test_cli_show_model_build_stats_prints_scheduler_events(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.yaml"
    input_file.write_text("apiVersion: alpha\n", encoding="utf-8")

    def fake_schedule(file_content, prettify, timeout, solver, progress_callback, model_build_stats_callback):
        assert progress_callback is None
        assert model_build_stats_callback is not None
        model_build_stats_callback(
            cli.scheduler.ModelBuildStats(
                step="create_shift_variables",
                elapsedSeconds=0.123456,
                variablesAdded=3,
                constraintsAdded=0,
                totalVariables=3,
                totalConstraints=0,
            )
        )
        model_build_stats_callback(
            cli.scheduler.ModelBuildStats(
                step="add_preference",
                elapsedSeconds=0.5,
                variablesAdded=2,
                constraintsAdded=4,
                totalVariables=5,
                totalConstraints=4,
                preferenceIndex=1,
                preferenceType="shift request",
            )
        )
        model_build_stats_callback(
            cli.scheduler.ModelBuildStats(
                step="add_preference",
                elapsedSeconds=0.25,
                variablesAdded=1,
                constraintsAdded=2,
                totalVariables=6,
                totalConstraints=6,
                preferenceIndex=2,
                preferenceType="shift request",
            )
        )
        return "large dataframe", {"large": "solution"}, 123, "FEASIBLE", {}

    monkeypatch.setattr(cli.scheduler, "schedule", fake_schedule)
    monkeypatch.setattr(cli, "_get_app_version", lambda: "v9.8.7-test")
    monkeypatch.setattr(sys, "argv", ["nurse-scheduling", str(input_file), "--show-model-build-stats"])

    cli.main()
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "nurse-scheduling v9.8.7-test"
    assert (
        "MODEL_BUILD_STATS\tstep\tcount\telapsed_seconds\tvariables_added\tconstraints_added"
        "\ttotal_variables\ttotal_constraints"
    ) in out
    assert "create_shift_variables\t1\t0.123456\t3\t0\t3\t0" in out
    assert "pref:shift request\t2\t0.750000\t3\t6\t6\t6" in out
    assert "large dataframe" not in out
    assert "large" not in out
    assert "Score: 123" in out
    assert "Status: FEASIBLE" in out
