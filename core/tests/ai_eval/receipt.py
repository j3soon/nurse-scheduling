"""Record prompt section hashes and reviewed comparison receipts in the prompt ledger."""

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

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.system_prompt import load_system_prompt_entries, load_system_prompt_sections

from .grading import load_cases
from .prompt_ladder import (
    STEPS_PATH,
    case_digest,
    evidence_input_digest,
    load_prompt_steps,
    prompt_at_step,
    validate_prompt_evidence,
)
from .runner import CASES, fixture_text

# The comparison's cost metric names and their keys in comparison statistics.
COST_KEYS = {
    "tool-calls": "tool_calls",
    "turns": "turns",
    "uncached-tokens": "uncached_prompt_tokens",
    "completion-tokens": "completion_tokens",
    "total-tokens": "total_tokens",
    "seconds": "seconds",
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _entry(entries: tuple[dict[str, Any], ...], step_id: str) -> dict[str, Any]:
    entry = next((entry for entry in entries if entry["id"] == step_id), None)
    if entry is None:
        raise ValueError(f"No prompt step has ID {step_id}")
    return entry


def refresh_hash(step_id: str, path: Path = STEPS_PATH) -> None:
    """Record an edited section's hash so that its new comparison can run."""
    entries = load_system_prompt_entries(path)
    sections = dict(zip((entry["id"] for entry in entries), load_system_prompt_sections(entries), strict=True))
    _entry(entries, step_id)["sha256"] = _sha256(sections[step_id])
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def build_receipt(report: Path, witness: str, note: str | None = None) -> tuple[str, dict[str, Any]]:
    """Build a receipt after checking that the report measured the current inputs.

    The witness gets the counts, model, and any cost gain. The report's other cases become controls.
    """
    comparison = json.loads((report / "comparison.json").read_text(encoding="utf-8"))
    measured = json.loads((report / "after" / "metadata.json").read_text(encoding="utf-8"))
    steps = load_prompt_steps()
    number = {step.id: number for number, step in enumerate(steps, 1)}[comparison["step"]]
    step = steps[number - 1]
    prefix = number if step.comparison_mode == "adjacent" else len(steps)
    if _sha256(prompt_at_step(prefix)) != measured["prompt_sha256"]:
        raise ValueError(f"The report did not measure the current {step.comparison_mode} prompt for {step.id}")
    if witness not in comparison["cases"]:
        raise ValueError(f"The report has no runs of {witness}")
    cases = {case.id: case for case in load_cases(CASES)}
    fixtures: dict[str, str] = {}
    observations = []
    for case_id, counts in comparison["cases"].items():
        case = cases[case_id]
        fixtures[case.fixture] = _sha256(fixture_text(case.fixture))
        measured_inputs = (measured["cases_sha256"][case_id], measured["fixtures_sha256"][case.fixture])
        if measured_inputs != (case_digest(case), fixtures[case.fixture]):
            raise ValueError(f"The testcase or fixture of {case_id} changed after the comparison")
        if counts["before"]["infrastructure_errors"] or counts["after"]["infrastructure_errors"]:
            raise ValueError(f"Infrastructure errors make {case_id} inconclusive. Rerun it")
        observations.append(
            {
                "case": case_id,
                "input_sha256": evidence_input_digest(step, case, fixtures[case.fixture]),
                "before": f"{counts['before']['passed']}/{counts['before']['runs']}",
                "after": f"{counts['after']['passed']}/{counts['after']['runs']}",
            }
        )
    record = next(observation for observation in observations if observation["case"] == witness)
    record |= {"model": measured["provider_model"], "infrastructure_errors": 0}
    counts = comparison["cases"][witness]
    # A cost gain counts only when every attempt in both arms passes.
    if comparison["cost_metric"] and counts["before"]["passed"] == counts["after"]["passed"] == counts["after"]["runs"]:
        cost = counts["metrics"][COST_KEYS[comparison["cost_metric"]]]
        if cost["missing_pairs"]:
            raise ValueError(f"{witness} has incomplete {comparison['cost_metric']} data")
        record |= {
            "cost_metric": comparison["cost_metric"],
            "cost_ratio": cost["after"]["mean"] / cost["before"]["mean"],
            "cost_target": comparison["cost_ratio"],
        }
    if controls := [observation for observation in observations if observation["case"] != witness]:
        record["controls"] = controls
    if note:
        record["note"] = note
    validate_prompt_evidence((replace(step, evidence=(record,)),), cases, fixtures)
    return step.id, record


def write_receipt(step_id: str, record: dict[str, Any], path: Path = STEPS_PATH) -> None:
    """Replace the step's receipt for the same witness, or add the receipt."""
    entries = load_system_prompt_entries(path)
    evidence = _entry(entries, step_id).setdefault("evidence", [])
    index = next((index for index, old in enumerate(evidence) if old["case"] == record["case"]), len(evidence))
    evidence[index : index + 1] = [record]
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    hash_command = commands.add_parser("hash", help="record an edited section's hash before comparing it")
    hash_command.add_argument("step", help="prompt step ID")
    write_command = commands.add_parser("write", help="record a reviewed comparison as a receipt")
    write_command.add_argument("report", type=Path, help="comparison output directory")
    write_command.add_argument("--case", required=True, help="witness testcase. Other report cases become controls")
    write_command.add_argument("--note", help="concise scope note")
    arguments = parser.parse_args(argv)
    if arguments.command == "hash":
        refresh_hash(arguments.step)
        return
    step_id, record = build_receipt(arguments.report.resolve(), arguments.case, arguments.note)
    write_receipt(step_id, record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
