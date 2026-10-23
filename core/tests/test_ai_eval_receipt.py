"""Test recording prompt ledger hashes and receipts from comparison reports."""

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

import hashlib
import json
import shutil
from dataclasses import replace

import pytest

from tests.ai_eval.grading import load_cases
from tests.ai_eval.prompt_ladder import (
    STEPS_PATH,
    case_digest,
    load_prompt_steps,
    prompt_at_step,
    validate_prompt_evidence,
)
from tests.ai_eval.receipt import build_receipt, helper_comparison, refresh_hash, uses_helper, write_receipt
from tests.ai_eval.runner import CASES, fixture_text

CASE_BY_ID = {case.id: case for case in load_cases(CASES)}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _report(tmp_path, step_number, witness_before=0, cost=None):
    steps = load_prompt_steps()
    step = steps[step_number - 1]
    cases = [CASE_BY_ID[case_id] for case_id in step.cases]
    prefix = step_number if step.comparison_mode == "adjacent" else len(steps)
    prompts = {
        "before": prompt_at_step(step_number - 1)
        if step.comparison_mode == "adjacent"
        else prompt_at_step(prefix, omit=step_number),
        "after": prompt_at_step(prefix),
    }
    for arm, prompt in prompts.items():
        (tmp_path / arm).mkdir()
        (tmp_path / arm / "metadata.json").write_text(
            json.dumps(
                {
                    "provider_model": "test-model",
                    "prompt_sha256": _sha256(prompt),
                    "cases_sha256": {case.id: case_digest(case) for case in cases},
                    "fixtures_sha256": {case.fixture: _sha256(fixture_text(case.fixture)) for case in cases},
                }
            ),
            encoding="utf-8",
        )

    def counts(passed):
        return {"runs": 3, "passed": passed, "infrastructure_errors": 0}

    (tmp_path / "comparison.json").write_text(
        json.dumps(
            {
                "step": step.id,
                "improved": True,
                "cases": {
                    case.id: {
                        "before": counts(witness_before if case.id == step.cases[0] else 3),
                        "after": counts(3),
                        "metrics": {"total_tokens": cost or {}},
                    }
                    for case in cases
                },
                "cost_metric": "total-tokens" if cost else None,
                "cost_ratio": 0.75 if cost else None,
            }
        ),
        encoding="utf-8",
    )
    return step


def test_receipt_replaces_the_witness_record_with_current_inputs(tmp_path):
    step_number = next(number for number, step in enumerate(load_prompt_steps(), 1) if len(step.cases) > 1)
    step = _report(tmp_path, step_number)
    ledger = tmp_path / "system-steps.json"
    shutil.copy(STEPS_PATH, ledger)
    step_id, record = build_receipt(tmp_path, step.cases[0], "Scope note.")
    write_receipt(step_id, record, ledger)

    written = load_prompt_steps(ledger)[step_number - 1]
    assert step_id == step.id
    assert record["before"] == "0/3" and record["model"] == "test-model" and record["note"] == "Scope note."
    assert {control["case"] for control in record["controls"]} == set(step.cases[1:])
    assert [old for old in written.evidence if old["case"] == record["case"]] == [record]


def test_receipt_records_a_cost_gain_for_a_passing_tie(tmp_path):
    step = _report(
        tmp_path, 1, witness_before=3, cost={"missing_pairs": 0, "before": {"mean": 4.0}, "after": {"mean": 1.0}}
    )
    _, record = build_receipt(tmp_path, step.cases[0])
    assert (record["cost_metric"], record["cost_ratio"], record["cost_target"]) == ("total-tokens", 0.25, 0.75)


@pytest.mark.parametrize("arm", ["before", "after"])
@pytest.mark.parametrize("field", ["cases_sha256", "fixtures_sha256", "prompt_sha256"])
def test_receipt_rejects_a_report_with_changed_inputs(tmp_path, arm, field):
    step = _report(tmp_path, 1)
    metadata_path = tmp_path / arm / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = "old" if field == "prompt_sha256" else dict.fromkeys(metadata[field], "old")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    message = "did not measure the current" if field == "prompt_sha256" else "changed after the comparison"
    with pytest.raises(ValueError, match=f"{arm}.*{message}"):
        build_receipt(tmp_path, step.cases[0])


def test_receipt_checks_the_omitted_section_in_an_ablation_baseline(tmp_path):
    number = next(number for number, step in enumerate(load_prompt_steps(), 1) if step.comparison_mode == "ablation")
    step = _report(tmp_path, number)
    assert build_receipt(tmp_path, step.cases[0])[0] == step.id
    metadata_path = tmp_path / "before" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["prompt_sha256"] = _sha256(prompt_at_step(number - 1))
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="before.*current ablation prompt"):
        build_receipt(tmp_path, step.cases[0])


def test_hash_refresh_records_the_current_section(tmp_path):
    ledger = tmp_path / "system-steps.json"
    entries = json.loads(STEPS_PATH.read_text(encoding="utf-8"))
    original = entries[0]["sha256"]
    entries[0]["sha256"] = "stale"
    ledger.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    refresh_hash(entries[0]["id"], ledger)
    assert json.loads(ledger.read_text(encoding="utf-8"))[0]["sha256"] == original
    assert ledger.read_text(encoding="utf-8") == STEPS_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "command,ok,result,used",
    [
        ("python /reference/tools/inspect_optimizer_result.py --statistics", True, "{}", True),
        ("python3 /reference/tools/inspect_optimizer_result.py --statistics | head -30", True, "{}", True),
        ("ls /reference/tools\npython /reference/tools/inspect_optimizer_result.py --statistics", True, "{}", True),
        ("python /reference/tools/inspect_optimizer_result.py", True, "{}", False),
        ("python /reference/tools/inspect_optimizer_result.py; echo --statistics", True, "{}", False),
        ("python /reference/tools/inspect_optimizer_result.py --statistics --help", True, "{}", False),
        ("cat /reference/tools/inspect_optimizer_result.py --statistics", True, "{}", False),
        ("echo 'python /reference/tools/inspect_optimizer_result.py --statistics'", True, "{}", False),
        ("python /reference/tools/inspect_optimizer_result.py --statistics", False, "{}", False),
        ("python /reference/tools/inspect_optimizer_result.py --statistics | head", True, "missing context", False),
        ("python /reference/tools/inspect_optimizer_result.py --statistics-extra", True, "{}", False),
        ("python /reference/tools/inspect_optimizer_result.py '--statistics", True, "{}", False),
    ],
)
def test_helper_use_requires_execution_target_flag_and_structured_output(command, ok, result, used):
    event = {"kind": "tool", "name": "bash", "ok": ok, "arguments": json.dumps({"command": command}), "result": result}
    assert uses_helper({"events": [event]}, "inspect_optimizer_result.py", ("--statistics",)) is used
    event["name"] = "read"
    assert not uses_helper({"events": [event]}, "inspect_optimizer_result.py", ("--statistics",))


def _helper_reports(tmp_path):
    for arm, tokens in (("before", 100), ("after", 60)):
        directory = tmp_path / arm
        (directory / "cases").mkdir(parents=True)
        (directory / "metadata.json").write_text(json.dumps({"provider_model": "test-model"}), encoding="utf-8")
        records = []
        for case_id in ("witness", "control"):
            for repetition in range(1, 4):
                record = {
                    "case_id": case_id,
                    "repetition": repetition,
                    "passed": True,
                    "error": "",
                    "token_usage": {"available": True, "complete": True, "completion_tokens": tokens},
                }
                records.append(record)
                trajectory = {
                    **record,
                    "question": case_id,
                    "fixture": "test",
                    "events": [
                        {
                            "kind": "tool",
                            "name": "bash",
                            "ok": True,
                            "arguments": json.dumps(
                                {"command": "python /reference/tools/inspect_optimizer_result.py --statistics"}
                            ),
                            "result": "{}",
                        }
                    ],
                }
                (directory / "cases" / f"{case_id}--run-{repetition}.json").write_text(
                    json.dumps(trajectory), encoding="utf-8"
                )
        (directory / "results.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
    return tmp_path / "before", tmp_path / "after"


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "wrong-answer",
        "no-flag",
        "discovery-only",
        "no-saving",
        "control-regression",
        "missing-usage",
        "infrastructure",
    ],
)
def test_helper_benefit_requires_correctness_execution_and_declared_savings(tmp_path, change):
    before, after = _helper_reports(tmp_path)
    records = [json.loads(line) for line in (after / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for record in records:
        path = after / "cases" / f"{record['case_id']}--run-{record['repetition']}.json"
        trajectory = json.loads(path.read_text(encoding="utf-8"))
        if change == "wrong-answer":
            record["passed"] = trajectory["passed"] = False
        if change == "infrastructure":
            record["error"] = trajectory["error"] = "sandbox unavailable"
        if change == "no-flag":
            trajectory["events"][0]["arguments"] = json.dumps(
                {"command": "python /reference/tools/inspect_optimizer_result.py"}
            )
        if change == "discovery-only":
            trajectory["events"][0]["arguments"] = json.dumps(
                {"command": "python /reference/tools/inspect_optimizer_result.py --statistics --help"}
            )
        if change == "no-saving":
            record["token_usage"]["completion_tokens"] = 99
        if change == "missing-usage":
            record["token_usage"]["complete"] = False
        if change == "control-regression" and record["case_id"] == "control":
            record["token_usage"]["completion_tokens"] = 120
        path.write_text(json.dumps(trajectory), encoding="utf-8")
    (after / "results.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    result = helper_comparison(
        before,
        after,
        ("witness",),
        "inspect_optimizer_result.py",
        ("--statistics",),
        metric="completion-tokens",
        max_ratio=0.9,
    )
    assert result["improved"] is (change == "none")
    assert result["helper_usage"]["after"]["witness"]["used"] == (0 if change in ("no-flag", "discovery-only") else 3)


def test_helper_comparison_rejects_changed_inputs_and_unpaired_repetitions(tmp_path):
    before, after = _helper_reports(tmp_path)
    path = after / "cases/witness--run-1.json"
    trajectory = json.loads(path.read_text(encoding="utf-8"))
    trajectory["question"] = "different question"
    path.write_text(json.dumps(trajectory), encoding="utf-8")
    with pytest.raises(ValueError, match="questions or fixtures"):
        helper_comparison(before, after, ("witness",), "inspect_optimizer_result.py")
    trajectory["question"] = "witness"
    path.write_text(json.dumps(trajectory), encoding="utf-8")
    records = [json.loads(line) for line in (after / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    records = [record for record in records if record["case_id"] != "witness" or record["repetition"] != 3]
    (after / "results.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(ValueError, match="three repetitions"):
        helper_comparison(before, after, ("witness",), "inspect_optimizer_result.py")


def test_helper_adoption_alone_is_not_a_benefit(tmp_path):
    before, after = _helper_reports(tmp_path)
    result = helper_comparison(before, after, ("witness",), "inspect_optimizer_result.py", ("--statistics",))
    assert result["helper_use_passed"]
    assert not result["improved"]


def test_unrelated_control_gain_cannot_establish_helper_benefit(tmp_path):
    before, after = _helper_reports(tmp_path)
    records = [json.loads(line) for line in (before / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for record in records:
        if record["case_id"] == "control":
            record["passed"] = False
    (before / "results.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    result = helper_comparison(before, after, ("witness",), "inspect_optimizer_result.py", ("--statistics",))
    assert result["helper_use_passed"]
    assert not result["improved"]


@pytest.mark.parametrize("change", ["none", "no-flag", "stale-helper", "incomplete-use"])
def test_prompt_receipt_can_require_helper_execution_and_flags(tmp_path, change):
    from nurse_scheduling.ai.workspace import REFERENCE_ATTACHMENT_TOOLS

    number = next(i for i, step in enumerate(load_prompt_steps(), 1) if len(step.cases) > 1)
    step = _report(tmp_path, number)
    helper = "inspect_optimizer_result.py"
    key = f"/reference/tools/{helper}"
    digest = hashlib.sha256(REFERENCE_ATTACHMENT_TOOLS[key].read_bytes()).hexdigest()
    for arm in ("before", "after"):
        directory = tmp_path / arm
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        metadata["references_sha256"] = {f"tools/{helper}": digest}
        (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (directory / "cases").mkdir()
        records = []
        for case_id in step.cases:
            for repetition in range(1, 4):
                record = {
                    "case_id": case_id,
                    "repetition": repetition,
                    "passed": arm == "after" or case_id != step.cases[0],
                    "error": "",
                }
                records.append(record)
                command = f"python {key}" + ("" if change == "no-flag" and arm == "after" else " --statistics")
                trajectory = {
                    **record,
                    "question": case_id,
                    "events": [
                        {
                            "kind": "tool",
                            "name": "bash",
                            "ok": True,
                            "arguments": json.dumps({"command": command}),
                            "result": "{}",
                        }
                    ],
                }
                (directory / "cases" / f"{case_id}--run-{repetition}.json").write_text(
                    json.dumps(trajectory), encoding="utf-8"
                )
        (directory / "results.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
    if change == "no-flag":
        with pytest.raises(ValueError, match="required flags"):
            build_receipt(tmp_path, step.cases[0], helper=helper, flags=("--statistics",))
        return
    _, record = build_receipt(tmp_path, step.cases[0], helper=helper, flags=("--statistics",))
    assert record["helper_usage"]["flags"] == ["--statistics"]
    assert record["helper_usage"]["cases"][0]["after"] == "3/3"
    if change == "stale-helper":
        record["helper_usage"]["sha256"] = "outdated"
    if change == "incomplete-use":
        record["helper_usage"]["cases"][0]["after"] = "2/3"
    cases = {case.id: case for case in load_cases(CASES)}
    fixtures = {case.fixture: _sha256(fixture_text(case.fixture)) for case in cases.values()}
    if change != "none":
        with pytest.raises(ValueError, match="stale helper|all after attempts"):
            validate_prompt_evidence((replace(step, evidence=(record,)),), cases, fixtures)
    else:
        validate_prompt_evidence((replace(step, evidence=(record,)),), cases, fixtures)


@pytest.mark.parametrize("decision", [False, None])
def test_receipt_rejects_a_failed_or_missing_comparison_decision(tmp_path, decision):
    step = _report(
        tmp_path, 1, witness_before=3, cost={"missing_pairs": 0, "before": {"mean": 100}, "after": {"mean": 50}}
    )
    path = tmp_path / "comparison.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["improved"] = decision
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="comparison.*benefit"):
        build_receipt(tmp_path, step.cases[0])


def test_saved_receipt_rejects_a_failed_comparison_or_regressing_control(tmp_path):
    number = next(i for i, step in enumerate(load_prompt_steps(), 1) if len(step.cases) > 1)
    step = _report(
        tmp_path, number, witness_before=3, cost={"missing_pairs": 0, "before": {"mean": 100}, "after": {"mean": 50}}
    )
    _, record = build_receipt(tmp_path, step.cases[0])
    assert record["comparison_passed"]
    assert record["controls"][0]["cost_ratio"] == 0.5
    fixtures = {case.fixture: _sha256(fixture_text(case.fixture)) for case in CASE_BY_ID.values()}
    record["controls"][0]["cost_ratio"] = 2
    with pytest.raises(ValueError, match="control.*cost regression"):
        validate_prompt_evidence((replace(step, evidence=(record,)),), CASE_BY_ID, fixtures)
    record["controls"][0]["cost_ratio"] = 0.5
    record["comparison_passed"] = False
    with pytest.raises(ValueError, match="comparison.*benefit"):
        validate_prompt_evidence((replace(step, evidence=(record,)),), CASE_BY_ID, fixtures)


def test_receipt_rechecks_control_costs_even_with_a_positive_decision(tmp_path):
    number = next(i for i, step in enumerate(load_prompt_steps(), 1) if len(step.cases) > 1)
    step = _report(
        tmp_path, number, witness_before=3, cost={"missing_pairs": 0, "before": {"mean": 100}, "after": {"mean": 50}}
    )
    path = tmp_path / "comparison.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["cases"][step.cases[1]]["metrics"]["total_tokens"]["after"]["mean"] = 200
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="cost regression"):
        build_receipt(tmp_path, step.cases[0])
