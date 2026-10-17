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

import pytest

from tests.ai_eval.grading import load_cases
from tests.ai_eval.prompt_ladder import STEPS_PATH, case_digest, load_prompt_steps, prompt_at_step
from tests.ai_eval.receipt import build_receipt, refresh_hash, write_receipt
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
