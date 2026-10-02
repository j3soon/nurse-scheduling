"""Test full ladder orchestration and preservation of incomplete evidence."""

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
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.ai_eval import ladder_audit, runner
from tests.ai_eval.prompt_ladder import load_prompt_steps


def test_audit_plan_reproduces_declared_contexts_and_only_ladder_cases(tmp_path):
    args, cases = runner._selected_cases(["--ladder-audit"])
    steps = load_prompt_steps()
    plan = ladder_audit.build_plan(
        steps, {case.id: case for case in cases}, tmp_path, repeat=args.repeat, jobs=args.jobs
    )
    assert args.repeat == 3 and args.jobs == 4
    assert plan["attempts"] == 3 * (2 * sum(len(step.cases) for step in steps) + len(cases))
    for cohort, step in zip(plan["cohorts"], steps, strict=False):
        flag = "--prompt-ablate-step" if step.comparison_mode == "ablation" else "--prompt-compare-step"
        assert cohort["args"][0] == flag
        assert cohort["args"][cohort["args"].index("--jobs") + 1] == "4"
        if any("cost_target" in receipt for receipt in step.evidence):
            assert "--cost-ratio" in cohort["args"]
    production = plan["cohorts"][-1]
    assert production["mode"] == "production"
    assert "--full" not in production["args"]
    assert production["args"].count("--case") == len(set(plan["cases"]))
    assert plan["fixture_sha256"] and plan["reference_sha256"] and plan["evaluation_sha256"]


@pytest.mark.parametrize(
    "flags",
    [
        ["--ladder-audit", "--case", "x"],
        ["--ladder-audit", "--prompt-step", "0"],
        ["--ladder-audit", "--baseline-report", "old"],
        ["--ladder-audit", "--continue-after-failure"],
        ["--ladder-audit", "--repeat", "1"],
        ["--plan-only", "--case", "x"],
    ],
)
def test_audit_rejects_conflicting_scope_before_provider_work(flags):
    with pytest.raises(SystemExit):
        runner._parse_args(flags)


def test_plan_only_needs_no_credentials_or_provider(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runner.AiSettings, "from_env", lambda: pytest.fail("provider settings requested"))
    assert runner.main(["--ladder-audit", "--plan-only", "--output-dir", str(tmp_path / "report")]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["cohorts"][-1]["name"] == "production"
    assert not (tmp_path / "report").exists()


def test_plan_rejects_inconsistent_predeclared_cost_targets(tmp_path):
    _args, cases = runner._selected_cases(["--ladder-audit"])
    step = replace(
        load_prompt_steps()[0],
        evidence=({"cost_metric": "seconds", "cost_target": 0.5}, {"cost_metric": "seconds", "cost_target": 0.6}),
    )
    with pytest.raises(ValueError, match="inconsistent cost targets"):
        ladder_audit.build_plan([step], {case.id: case for case in cases}, tmp_path, repeat=3, jobs=4)


def _plan(root):
    return {
        "attempts": 9,
        "cohorts": [
            {"name": "section", "mode": "adjacent", "args": ["--output-dir", str(root / "section")]},
            {"name": "production", "mode": "production", "args": ["--output-dir", str(root / "production")]},
        ],
    }


def _executor(calls, *, improved=True, after_pass=3, infrastructure=0, missing=False, changed=None):
    def execute(command, **kwargs):
        calls.append(command)
        directory = Path(command[command.index("--output-dir") + 1])
        if changed is not None:
            changed.append(True)
        if missing:
            return SimpleNamespace(returncode=2)
        directory.mkdir()
        if directory.name == "production":
            (directory / "results.jsonl").write_text(
                json.dumps({"case_id": "witness", "passed": True, "error": ""}) + "\n"
            )
            return SimpleNamespace(returncode=0)
        record = {
            "improved": improved,
            "cases": {
                "witness": {
                    "before": {"passed": 0, "runs": 3, "infrastructure_errors": infrastructure},
                    "after": {"passed": after_pass, "runs": 3, "infrastructure_errors": 0},
                    "metrics": {"completion_tokens": {"delta": {"mean": -20, "std": 3}}},
                }
            },
        }
        (directory / "comparison.json").write_text(json.dumps(record))
        return SimpleNamespace(returncode=0 if improved else 1)

    return execute


@pytest.mark.parametrize(
    ("options", "status", "code"),
    [
        ({}, "benefit reproduced", 0),
        ({"improved": False}, "benefit not reproduced", 1),
        ({"improved": False, "after_pass": 2}, "after behavioral failure", 1),
        ({"improved": False, "infrastructure": 1}, "infrastructure error", 1),
    ],
)
def test_audit_continues_completed_failures_and_reports_first_class_metrics(tmp_path, options, status, code):
    root = tmp_path / "audit"
    calls = []
    assert ladder_audit.run_audit(_plan(root), root, execute=_executor(calls, **options)) == code
    assert len(calls) == 2
    audit = json.loads((root / "audit.json").read_text())
    assert audit["results"][0]["status"] == status
    assert audit["results"][1]["status"] == "pass"
    assert audit["results"][0]["cases"]["witness"]["metrics"]["completion_tokens"]["delta"]["std"] == 3
    assert "section/comparison.md" in (root / "summary.md").read_text()
    assert len(list((root / "logs").glob("*.log"))) == 2


def test_missing_report_stops_without_running_more_cases(tmp_path):
    root = tmp_path / "audit"
    calls = []
    assert ladder_audit.run_audit(_plan(root), root, execute=_executor(calls, missing=True)) == 2
    assert len(calls) == 1
    audit = json.loads((root / "audit.json").read_text())
    assert audit["status"] == "incomplete"
    assert audit["results"][0]["exit_code"] == 2
    assert (root / "plan.json").exists()


def test_changed_inputs_stop_with_original_report_retained(tmp_path):
    root = tmp_path / "audit"
    calls, changed = [], []
    assert (
        ladder_audit.run_audit(
            _plan(root), root, execute=_executor(calls, changed=changed), unchanged=lambda: not changed
        )
        == 2
    )
    assert len(calls) == 1
    assert (root / "section/comparison.json").exists()
    assert json.loads((root / "audit.json").read_text())["status"] == "incomplete: inputs changed"


def test_existing_audit_is_never_overwritten(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    with pytest.raises(FileExistsError):
        ladder_audit.run_audit(_plan(root), root, execute=lambda *args, **kwargs: pytest.fail("started evaluation"))


@pytest.mark.parametrize("mode", ["adjacent", "production"])
def test_report_missing_a_planned_case_is_incomplete(tmp_path, mode):
    root = tmp_path / "audit"
    calls = []
    name = "production" if mode == "production" else "section"
    cohort = {
        "name": name,
        "mode": mode,
        "args": ["--case", "missing-case", "--repeat", "3", "--output-dir", str(root / name)],
    }
    plan = {"attempts": 3, "cohorts": [cohort]}
    assert ladder_audit.run_audit(plan, root, execute=_executor(calls)) == 2
    assert json.loads((root / "audit.json").read_text())["results"][0]["status"] == "incomplete report"
