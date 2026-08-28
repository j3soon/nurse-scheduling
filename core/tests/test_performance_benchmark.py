"""Tests for the opt-in real-case performance benchmark harness."""

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

import json
from argparse import Namespace
from types import SimpleNamespace

from nurse_scheduling.solver_interface import SchedulePhaseProgress, SolverProgress
from tests.real import performance_benchmark


def test_summarize_runs_reports_score_time_and_target_distributions():
    runs = [
        {
            "score": 100,
            "solverSeconds": 5.0,
            "endToEndSeconds": 6.0,
            "targetReached": True,
            "targetSolverSeconds": 4.0,
            "targetEndToEndSeconds": 5.0,
        },
        {
            "score": 120,
            "solverSeconds": 5.2,
            "endToEndSeconds": 6.4,
            "targetReached": True,
            "targetSolverSeconds": 3.0,
            "targetEndToEndSeconds": 4.0,
        },
        {"score": None, "error": "failed"},
    ]

    summary = performance_benchmark._summarize_runs(runs, target_score=90)

    assert summary["requestedRuns"] == 3
    assert summary["completedRuns"] == 2
    assert summary["score"] == {
        "count": 2,
        "min": 100,
        "median": 110.0,
        "mean": 110.0,
        "max": 120,
        "sampleVariance": 200,
        "sampleStandardDeviation": 14.142136,
        "coefficientOfVariationPercent": 12.856487,
    }
    assert summary["targetReachedRuns"] == 2
    assert summary["targetSolverSeconds"]["median"] == 3.5
    assert summary["targetEndToEndSeconds"]["median"] == 4.5


def test_child_records_progress_and_stops_at_target(tmp_path, monkeypatch):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_bytes(b"scenario")
    should_stop_seen = False

    def fake_schedule(file_content, prettify, solver, timeout, progress_callback, should_stop):
        nonlocal should_stop_seen
        assert file_content
        assert prettify is False
        assert solver == "ortools/cp-sat"
        assert timeout == 10
        progress_callback(SchedulePhaseProgress("scheduler", "solving", "Solving", 1.0))
        progress_callback(SolverProgress("ortools/cp-sat:solution-callback", 123, 2.5, solutionIndex=1))
        should_stop_seen = should_stop()
        progress_callback(SchedulePhaseProgress("scheduler", "exporting", "Exporting", 3.6))
        return SimpleNamespace(score=123, solver_status="FEASIBLE")

    monkeypatch.setattr(performance_benchmark.nurse_scheduling, "schedule", fake_schedule)
    monkeypatch.setattr(performance_benchmark, "REAL_TESTCASE", scenario_path)
    args = Namespace(
        mode=performance_benchmark.SEARCH_MODE,
        run_dir=run_dir,
        run_number=1,
        warmup=False,
        started_at="2026-08-28T00:00:00+00:00",
        timeout=10,
        target_score=120,
    )

    assert performance_benchmark._run_child(args) == 0
    assert should_stop_seen is True
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert result["targetReached"] is True
    assert result["targetSolverSeconds"] == 2.5
    assert result["score"] == 123
    assert result["solverSeconds"] == 2.6
    progress = [json.loads(line) for line in (run_dir / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["source"] for event in progress] == [
        "scheduler",
        "ortools/cp-sat:solution-callback",
        "scheduler",
    ]


def test_compute_child_calculates_attainment_score(tmp_path, monkeypatch):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_bytes(b"scenario")
    monkeypatch.setattr(performance_benchmark, "ATTAINMENT_THRESHOLDS", (10, 20))

    def fake_schedule(file_content, prettify, solver, timeout, progress_callback, should_stop):
        assert file_content
        assert prettify is False
        assert solver == "ortools/cp-sat"
        assert timeout == 10
        progress_callback(SchedulePhaseProgress("scheduler", "solving", "Solving", 1.0))
        progress_callback(SolverProgress("ortools/cp-sat:solution-callback", 15, 2.0, solutionIndex=1))
        assert should_stop() is False
        progress_callback(SolverProgress("ortools/cp-sat:solution-callback", 25, 6.0, solutionIndex=2))
        assert should_stop() is True
        progress_callback(SchedulePhaseProgress("scheduler", "exporting", "Exporting", 7.0))
        return SimpleNamespace(score=25, solver_status="FEASIBLE")

    monkeypatch.setattr(performance_benchmark.nurse_scheduling, "schedule", fake_schedule)
    monkeypatch.setattr(performance_benchmark, "REAL_TESTCASE", scenario_path)
    args = Namespace(
        mode=performance_benchmark.COMPUTE_MODE,
        run_dir=run_dir,
        run_number=1,
        warmup=False,
        started_at="2026-08-28T00:00:00+00:00",
        timeout=10,
        target_score=None,
    )

    assert performance_benchmark._run_child(args) == 0
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert result["completedCriterion"] is True
    assert result["stopReason"] == "top_threshold"
    assert result["attainmentScore"] == 60.0
    assert result["thresholdReachSeconds"] == {"10": 2.0, "20": 6.0}
    assert result["solverSeconds"] == 6.0


def test_compute_markdown_reports_final_machine_score():
    report = {
        "config": {"warmupRuns": 1, "runs": 2, "timeoutSeconds": 300},
        "environment": {
            "appVersion": "test",
            "ortoolsVersion": "test",
            "cpuModel": "test CPU",
            "cpuAffinity": [0, 1],
            "logicalCpuCount": 2,
        },
        "runs": [],
        "summary": {
            "attainmentScore": {
                "mean": 86.798927,
                "median": 87.0,
                "min": 83.0,
                "max": 89.0,
                "sampleStandardDeviation": 2.0,
            }
        },
    }

    markdown = performance_benchmark._markdown_compute_report(report)

    assert "- Final machine score: **86.798927**" in markdown


def test_parse_args_uses_documented_defaults():
    args = performance_benchmark._parse_args([])

    assert args.mode == "compute"
    assert args.runs == 5
    assert args.warmup_runs == 1
    assert args.timeout == 300
    assert args.target_score is None
    assert "performance-benchmarks" in args.output_dir.parts
