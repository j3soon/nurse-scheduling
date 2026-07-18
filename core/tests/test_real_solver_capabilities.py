"""Tests for the opt-in real solver capability probe."""

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

from types import SimpleNamespace

from tests.real import solver_capabilities


def _job(
    *,
    state="completed",
    result=None,
    error=None,
    schedule="/optimize/job/xlsx",
):
    return {
        "id": "job",
        "state": state,
        "terminal": state in {"completed", "cancelled", "failed"},
        "result": result,
        "error": error,
        "links": {"schedule": schedule},
    }


def test_probe_defaults_and_round_order():
    args = solver_capabilities.build_parser().parse_args(["--solver", "ortools/cp-sat"])
    config = solver_capabilities._config_from_args(args)

    assert solver_capabilities.ROUND_ORDER == ("timeout", "cancel", "finish-now", "intermediate-scores")
    assert solver_capabilities.CONFIRMED_SOLVER_CHOICES == tuple(
        capabilities.value for capabilities in solver_capabilities.SOLVER_CAPABILITIES
    )
    assert config.timeout_seconds == 10
    assert config.timeout_grace_seconds == 90
    assert config.cbc_intermediate_score_testcase == solver_capabilities.CBC_INTERMEDIATE_SCORE_TESTCASE
    assert config.control_timeout_seconds == 60
    assert config.cancel_delay_seconds == 2
    assert config.finish_wait_seconds == 10


def test_probe_solver_runs_rounds_in_order(monkeypatch):
    calls = []

    def fake_round(name, solver, _config):
        calls.append((name, solver))
        return solver_capabilities.RoundReport(name, "PASS", "ok", solver_available=True)

    monkeypatch.setattr(solver_capabilities, "_run_round_subprocess", fake_round)

    report = solver_capabilities.probe_solver("ORTOOLS/CP-SAT", solver_capabilities.ProbeConfig())

    assert calls == [
        ("timeout", "ortools/cp-sat"),
        ("cancel", "ortools/cp-sat"),
        ("finish-now", "ortools/cp-sat"),
        ("intermediate-scores", "ortools/cp-sat"),
    ]
    assert [round_report.name for round_report in report.rounds] == list(solver_capabilities.ROUND_ORDER)
    assert report.available is True


def test_unavailable_timeout_skips_remaining_subprocesses(monkeypatch):
    calls = []

    def fake_round(name, _solver, _config):
        calls.append(name)
        return solver_capabilities.RoundReport(name, "UNAVAILABLE", "missing", solver_available=False)

    monkeypatch.setattr(solver_capabilities, "_run_round_subprocess", fake_round)

    report = solver_capabilities.probe_solver("pulp/cuopt", solver_capabilities.ProbeConfig())

    assert calls == ["timeout"]
    assert [round_report.status for round_report in report.rounds] == [
        "UNAVAILABLE",
        "NOT_CONFIRMED",
        "NOT_CONFIRMED",
        "UNAVAILABLE",
    ]
    assert report.available is False


def test_probe_runs_only_capabilities_confirmed_by_registry(monkeypatch):
    calls = []

    def fake_round(name, _solver, _config):
        calls.append(name)
        return solver_capabilities.RoundReport(name, "PASS", "ok", solver_available=True)

    monkeypatch.setattr(solver_capabilities, "_run_round_subprocess", fake_round)

    report = solver_capabilities.probe_solver("pulp/cbc", solver_capabilities.ProbeConfig())

    assert calls == ["timeout", "intermediate-scores"]
    assert [round_report.status for round_report in report.rounds] == [
        "PASS",
        "NOT_CONFIRMED",
        "NOT_CONFIRMED",
        "PASS",
    ]


def test_timeout_result_classification():
    config = solver_capabilities.ProbeConfig(timeout_seconds=10, timeout_grace_seconds=5)
    feasible = _job(
        result={
            "outcome": "feasible",
            "solver_status": "FEASIBLE",
            "termination_reason": "limit_or_stop",
        }
    )
    optimal = _job(
        result={
            "outcome": "optimal",
            "solver_status": "OPTIMAL",
            "termination_reason": "optimality_proven",
        }
    )
    no_solution = _job(
        state="failed",
        result=None,
        error={"code": "no_solution_found", "message": "No schedule"},
        schedule=None,
    )
    watchdog = _job(
        state="failed",
        result=None,
        error={
            "code": "timeout_forced",
            "message": "Process terminated",
        },
        schedule=None,
    )

    assert solver_capabilities._evaluate_timeout(feasible, 10.2, config).status == "PASS"
    assert solver_capabilities._evaluate_timeout(no_solution, 9.8, config).status == "PASS"
    assert solver_capabilities._evaluate_timeout(watchdog, 14.9, config).status == "PASS"
    assert solver_capabilities._evaluate_timeout(optimal, 1.0, config).status == "INCONCLUSIVE"
    assert solver_capabilities._evaluate_timeout(feasible, 15.1, config).status == "FAIL"


def test_only_cbc_intermediate_round_uses_simple_testcase(monkeypatch):
    seen = []

    def fake_submit(_client, testcase, _solver, _timeout):
        seen.append(testcase)
        return {"id": "job"}

    monkeypatch.setattr(solver_capabilities, "_submit_job", fake_submit)
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_for_solving",
        lambda *_args: (None, None, _job(state="failed", result=None, schedule=None)),
    )
    config = solver_capabilities.ProbeConfig()

    assert solver_capabilities.REAL_SCENARIO_UNSUITABLE_SOLVERS == {"pulp/cbc"}
    for solver in ("ortools/cp-sat", "pulp/cuopt", "pulp/cbc"):
        solver_capabilities._run_timeout_round(object(), object(), solver, config)
        solver_capabilities._run_intermediate_scores_round(object(), object(), solver, config)

    assert seen == [
        config.testcase,
        config.testcase,
        config.testcase,
        config.testcase,
        config.testcase,
        config.cbc_intermediate_score_testcase,
    ]


def test_graceful_cancel_round_checks_terminal_result(monkeypatch):
    monkeypatch.setattr(
        solver_capabilities,
        "_submit_job",
        lambda *_args: _job(state="queued", result=None, error=None, schedule=None),
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_for_solving",
        lambda *_args: (100.0, "2", _job(state="running", result=None, error=None, schedule=None)),
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_before_control",
        lambda *_args, **_kwargs: (False, _job(state="running", result=None, error=None, schedule=None)),
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_for_terminal",
        lambda *_args: _job(
            state="cancelled",
            result=None,
            error={"code": "cancelled", "message": "cancelled"},
            schedule=None,
        ),
    )
    client = SimpleNamespace(post=lambda _path: SimpleNamespace(status_code=202))

    report = solver_capabilities._run_control_round(
        "cancel",
        client,
        object(),
        "ortools/cp-sat",
        solver_capabilities.ProbeConfig(),
    )

    assert report.status == "PASS"
    assert report.terminal_state == "cancelled"
    assert report.artifact_available is False


def test_graceful_cancel_round_rejects_forced_cancellation():
    report = solver_capabilities._evaluate_graceful_cancel(
        _job(
            state="cancelled",
            result=None,
            error={"code": "cancelled_forced", "message": "Process terminated"},
            schedule=None,
        ),
        15.0,
    )

    assert report.status == "FAIL"
    assert report.detail == ("The server forced cancellation, so the solver did not demonstrate graceful cancellation.")


def test_finish_now_without_incumbent_is_inconclusive(monkeypatch):
    monkeypatch.setattr(
        solver_capabilities,
        "_submit_job",
        lambda *_args: _job(state="queued", result=None, error=None, schedule=None),
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_for_solving",
        lambda *_args: (100.0, "2", _job(state="running", result=None, error=None, schedule=None)),
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_before_control",
        lambda *_args, **_kwargs: (False, _job(state="running", result=None, error=None, schedule=None)),
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_for_terminal",
        lambda *_args: _job(
            state="failed",
            result=None,
            error={"code": "no_solution_found", "message": "No schedule"},
            schedule=None,
        ),
    )
    client = SimpleNamespace(post=lambda _path: SimpleNamespace(status_code=202))

    report = solver_capabilities._run_control_round(
        "finish-now",
        client,
        object(),
        "ortools/cp-sat",
        solver_capabilities.ProbeConfig(),
    )

    assert report.status == "INCONCLUSIVE"
    assert report.error_code == "no_solution_found"


def test_intermediate_score_round_requires_progress_event(monkeypatch):
    terminal = _job(
        result={
            "outcome": "feasible",
            "solver_status": "FEASIBLE",
            "termination_reason": "limit_or_stop",
        }
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_submit_job",
        lambda *_args: {"id": "job"},
    )
    monkeypatch.setattr(
        solver_capabilities,
        "_wait_for_solving",
        lambda *_args: (100.0, "2", _job(state="running", result=None, schedule=None)),
    )
    store = SimpleNamespace(
        stream_events=lambda *_args, **_kwargs: iter(
            [SimpleNamespace(type="job.progressed", data={"source": "ortools/cp-sat:solution-callback"})]
        ),
    )
    client = SimpleNamespace(get=lambda _path: SimpleNamespace(json=lambda: terminal))

    report = solver_capabilities._run_intermediate_scores_round(
        client,
        store,
        "ortools/cp-sat",
        solver_capabilities.ProbeConfig(),
    )

    assert report.status == "PASS"
    assert report.solver_available is True


def test_markdown_report_uses_requested_column_order():
    rounds = tuple(
        solver_capabilities.RoundReport(name, "PASS", "ok", solver_available=True)
        for name in solver_capabilities.ROUND_ORDER
    )
    markdown = solver_capabilities.render_markdown([solver_capabilities.SolverReport("ortools/cp-sat", True, rounds)])

    assert markdown.splitlines()[0] == (
        "| Selector | Available | Timeout | Graceful cancel | Finish now | Intermediate scores | Notes |"
    )
    assert "`ortools/cp-sat` | Yes | PASS | PASS | PASS | PASS" in markdown
