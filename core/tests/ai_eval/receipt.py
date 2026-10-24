"""Record prompt receipts and check helper adoption against correctness and cost."""

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
import re
import shlex
from dataclasses import replace
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.system_prompt import load_system_prompt_entries, load_system_prompt_sections

from .comparison import comparison_statistics
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


def build_receipt(
    report: Path,
    witness: str,
    note: str | None = None,
    *,
    helper: str | None = None,
    flags: tuple[str, ...] = (),
    helper_cases: tuple[str, ...] = (),
) -> tuple[str, dict[str, Any]]:
    """Build a receipt after checking that the report measured the current inputs.

    The witness gets the counts, model, and any cost gain. The report's other cases become controls.
    """
    comparison = json.loads((report / "comparison.json").read_text(encoding="utf-8"))
    if comparison.get("improved") is not True:
        raise ValueError("The complete comparison did not demonstrate a benefit")
    measured = {
        arm: json.loads((report / arm / "metadata.json").read_text(encoding="utf-8")) for arm in ("before", "after")
    }
    steps = load_prompt_steps()
    number = {step.id: number for number, step in enumerate(steps, 1)}[comparison["step"]]
    step = steps[number - 1]
    prefix = number if step.comparison_mode == "adjacent" else len(steps)
    prompts = {
        "before": prompt_at_step(number - 1)
        if step.comparison_mode == "adjacent"
        else prompt_at_step(prefix, omit=number),
        "after": prompt_at_step(prefix),
    }
    for arm, prompt in prompts.items():
        if _sha256(prompt) != measured[arm]["prompt_sha256"]:
            raise ValueError(
                f"The {arm} report did not measure the current {step.comparison_mode} prompt for {step.id}"
            )
    if witness not in comparison["cases"]:
        raise ValueError(f"The report has no runs of {witness}")
    cases = {case.id: case for case in load_cases(CASES)}
    fixtures: dict[str, str] = {}
    observations = []
    for case_id, counts in comparison["cases"].items():
        case = cases[case_id]
        fixtures[case.fixture] = _sha256(fixture_text(case.fixture))
        for arm, metadata in measured.items():
            measured_inputs = (metadata["cases_sha256"][case_id], metadata["fixtures_sha256"][case.fixture])
            if measured_inputs != (case_digest(case), fixtures[case.fixture]):
                raise ValueError(f"The {arm} testcase or fixture of {case_id} changed after the comparison")
        if counts["before"]["infrastructure_errors"] or counts["after"]["infrastructure_errors"]:
            raise ValueError(f"Infrastructure errors make {case_id} inconclusive. Rerun it")
        if (
            comparison["cost_metric"]
            and counts["before"]["passed"] == counts["after"]["passed"] == counts["after"]["runs"]
        ):
            cost = counts["metrics"][COST_KEYS[comparison["cost_metric"]]]
            if cost["missing_pairs"] or not cost["before"]["mean"]:
                raise ValueError(f"{case_id} has incomplete {comparison['cost_metric']} data")
            ratio = cost["after"]["mean"] / cost["before"]["mean"]
            if ratio > 1:
                raise ValueError(f"Control {case_id} has a cost regression")
        else:
            ratio = None
        observations.append(
            {
                "case": case_id,
                "input_sha256": evidence_input_digest(step, case, fixtures[case.fixture]),
                "before": f"{counts['before']['passed']}/{counts['before']['runs']}",
                "after": f"{counts['after']['passed']}/{counts['after']['runs']}",
                **({"cost_ratio": ratio} if ratio is not None else {}),
            }
        )
    record = next(observation for observation in observations if observation["case"] == witness)
    record |= {"model": measured["after"]["provider_model"], "infrastructure_errors": 0, "comparison_passed": True}
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
    if helper:
        checked = helper_comparison(report / "before", report / "after", helper_cases or (witness,), helper, flags)
        if not checked["helper_use_passed"]:
            raise ValueError("Candidate runs did not execute the helper with all required flags")
        record["helper_usage"] = {
            "helper": helper,
            "sha256": measured["after"]["references_sha256"][f"tools/{helper}"],
            "flags": list(flags),
            "cases": [
                {
                    "case": case_id,
                    **{
                        arm: f"{usage[case_id]['used']}/{usage[case_id]['runs']}"
                        for arm, usage in checked["helper_usage"].items()
                    },
                }
                for case_id in checked["helper_usage"]["after"]
            ],
        }
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


def uses_helper(trajectory: dict[str, Any], helper: str, flags: tuple[str, ...] = ()) -> bool:
    """Count one successful direct invocation with output attributable to the helper."""
    for event in trajectory.get("events", []):
        if (
            event.get("kind") != "tool"
            or event.get("name") != "bash"
            or event.get("ok") is not True
            or event.get("seeded")
        ):
            continue
        try:
            command = json.loads(event.get("arguments", ""))["command"]
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(command, str):
            continue
        # Compound commands do not identify which process produced JSON or succeeded.
        # Keep those forms for manual review instead of inferring shell execution.
        lexer = shlex.shlex(command.strip(), posix=True, punctuation_chars=";&|()<>\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            words = list(lexer)
        except ValueError:
            continue
        if any((word and all(char in ";&|()<>\n" for char in word)) or "$" in word or "`" in word for word in words):
            continue
        if len(words) < 2 or not re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)*)?", Path(words[0]).name):
            continue
        if words[1] != f"/reference/tools/{helper}":
            continue
        options = {word.split("=", 1)[0] for word in words[2:]}
        if not options.intersection({"-h", "--help"}) and set(flags) <= options:
            output = str(event.get("result", ""))
            for line in (output, *output.splitlines()):
                try:
                    if isinstance(json.loads(line), dict):
                        return True
                except ValueError:
                    continue
    return False


def helper_comparison(
    before: Path,
    after: Path,
    cases: tuple[str, ...],
    helper: str,
    flags: tuple[str, ...] = (),
    *,
    metric: str | None = None,
    max_ratio: float | None = None,
) -> dict[str, Any]:
    """Check adoption in addition to the existing correctness and cost criteria."""
    if (metric is None) != (max_ratio is None) or (max_ratio is not None and not 0 < max_ratio < 1):
        raise ValueError("Specify a cost metric and a ratio strictly between zero and one together")
    if not cases or len(set(cases)) != len(cases):
        raise ValueError("Select distinct helper-use cases")
    records, metadata, usage = {}, {}, {}
    for arm, directory in (("before", before), ("after", after)):
        metadata[arm] = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        records[arm] = [
            json.loads(line) for line in (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        usage[arm] = {}
        for case_id in cases:
            selected = [record for record in records[arm] if record["case_id"] == case_id]
            if len(selected) < 3:
                raise ValueError(f"{arm} {case_id} needs at least three repetitions")
            used = 0
            for record in selected:
                path = directory / "cases" / f"{case_id}--run-{record['repetition']}.json"
                trajectory = json.loads(path.read_text(encoding="utf-8"))
                if any(trajectory.get(key) != record.get(key) for key in ("case_id", "repetition", "passed", "error")):
                    raise ValueError("Trajectory and result record disagree")
                used += uses_helper(trajectory, helper, flags)
            usage[arm][case_id] = {"used": used, "runs": len(selected)}
    if {record["case_id"] for record in records["before"]} != {record["case_id"] for record in records["after"]}:
        raise ValueError("Compared reports contain different case sets")
    for case_id in {record["case_id"] for record in records["before"]}:
        source_inputs = []
        for directory in (before, after):
            path = directory / "cases" / f"{case_id}--run-1.json"
            trajectory = json.loads(path.read_text(encoding="utf-8"))
            source_inputs.append({key: trajectory.get(key) for key in ("question", "user_turns", "fixture")})
        if source_inputs[0] != source_inputs[1]:
            raise ValueError(f"Compared questions or fixtures changed for {case_id}")
    if metadata["before"].get("fixtures_sha256") != metadata["after"].get("fixtures_sha256"):
        raise ValueError("Compared fixture bytes changed")
    summary = comparison_statistics(records["before"], records["after"])
    valid, gain = True, False
    for case_id, result in summary["cases"].items():
        left, right = result["before"], result["after"]
        paired = result["matched_pairs"] >= 3 and not result["unmatched_before"] and not result["unmatched_after"]
        valid &= paired and not left["infrastructure_errors"] and not right["infrastructure_errors"]
        valid &= right["passed"] == right["runs"]
        gain |= case_id in cases and right["passed"] > left["passed"]
        if metric and left["passed"] == left["runs"] and right["passed"] == right["runs"]:
            cost = result["metrics"][COST_KEYS[metric]]
            ratio = None if cost["relative_delta"] is None else cost["relative_delta"] + 1
            valid &= not cost["missing_pairs"] and ratio is not None and ratio <= 1
            gain |= case_id in cases and ratio is not None and ratio <= max_ratio
    if metadata["before"]["provider_model"] != metadata["after"]["provider_model"]:
        raise ValueError("Compared reports use different provider models")
    adoption = all(counts["used"] == counts["runs"] for counts in usage["after"].values())
    return {
        **summary,
        "helper": helper,
        "flags": list(flags),
        "helper_usage": usage,
        "metadata": metadata,
        "cost_metric": metric,
        "cost_ratio": max_ratio,
        "benefit_passed": bool(valid and gain),
        "helper_use_passed": adoption,
        "improved": bool(valid and gain and adoption),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    hash_command = commands.add_parser("hash", help="record an edited section's hash before comparing it")
    hash_command.add_argument("step", help="prompt step ID")
    write_command = commands.add_parser("write", help="record a reviewed comparison as a receipt")
    write_command.add_argument("report", type=Path, help="comparison output directory")
    write_command.add_argument("--case", required=True, help="witness testcase. Other report cases become controls")
    write_command.add_argument("--note", help="concise scope note")
    write_command.add_argument("--helper", help="also require actual helper execution in the saved receipt")
    write_command.add_argument("--flag", action="append", default=[], help="required helper option")
    write_command.add_argument("--helper-case", action="append", default=[], help="case requiring helper execution")
    helper_command = commands.add_parser(
        "check-helper", help="check helper execution, correctness and declared cost benefit"
    )
    helper_command.add_argument("before", type=Path)
    helper_command.add_argument("after", type=Path)
    helper_command.add_argument("--case", action="append", required=True, help="case requiring helper execution")
    helper_command.add_argument("--helper", required=True, help="helper filename in /reference/tools")
    helper_command.add_argument(
        "--flag", action="append", default=[], help="required option, such as --flag=--statistics"
    )
    helper_command.add_argument("--cost-metric", choices=COST_KEYS)
    helper_command.add_argument("--cost-ratio", type=float)
    helper_command.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "check-helper":
        record = helper_comparison(
            arguments.before,
            arguments.after,
            tuple(arguments.case),
            arguments.helper,
            tuple(arguments.flag),
            metric=arguments.cost_metric,
            max_ratio=arguments.cost_ratio,
        )
        arguments.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: record[key] for key in ("helper_use_passed", "benefit_passed", "improved")}))
        raise SystemExit(0 if record["improved"] else 1)
    if arguments.command == "hash":
        refresh_hash(arguments.step)
        return
    step_id, record = build_receipt(
        arguments.report.resolve(),
        arguments.case,
        arguments.note,
        helper=arguments.helper,
        flags=tuple(arguments.flag),
        helper_cases=tuple(arguments.helper_case),
    )
    write_receipt(step_id, record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
