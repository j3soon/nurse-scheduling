"""Audit every prompt section and the complete production prompt."""

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
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.system_prompt import compose_system_prompt

from .grading import EvalCase
from .prompt_ladder import PromptStep, case_digest


def build_plan(
    steps: Sequence[PromptStep], cases: Mapping[str, EvalCase], root: Path, *, repeat: int, jobs: int
) -> dict[str, Any]:
    """Freeze the declared comparison modes, cases, and cost targets before execution."""
    from .runner import _reference_digests, fixture_text

    case_ids = list(dict.fromkeys(case for step in steps for case in step.cases))
    if not case_ids or any(case not in cases for case in case_ids):
        raise ValueError("Ladder cases must be nonempty and all exist")
    if any(not step.cases for step in steps):
        raise ValueError("Every ladder section needs targeted cases")
    cohorts = []
    for number, step in enumerate(steps, 1):
        name = f"{number:02d}-{step.id}"
        flag = "--prompt-ablate-step" if step.comparison_mode == "ablation" else "--prompt-compare-step"
        args = [flag, str(number)]
        for case in step.cases:
            args.extend(["--case", case])
        targets = {
            (record["cost_metric"], record["cost_target"]) for record in step.evidence if "cost_target" in record
        }
        if len(targets) > 1:
            raise ValueError(f"Section {step.id} has inconsistent cost targets")
        if targets:
            metric, target = targets.pop()
            args.extend(["--cost-metric", metric, "--cost-ratio", str(target)])
        cohorts.append({"name": name, "mode": step.comparison_mode, "args": args})
    args = [value for case in case_ids for value in ("--case", case)]
    cohorts.append({"name": "production", "mode": "production", "args": args})
    for cohort in cohorts:
        cohort["args"].extend(
            ["--repeat", str(repeat), "--jobs", str(jobs), "--output-dir", str(root / cohort["name"])]
        )
    return {
        "repeat": repeat,
        "jobs": jobs,
        "cases": case_ids,
        "prompt_sha256": hashlib.sha256(compose_system_prompt().encode()).hexdigest(),
        "case_sha256": {case: case_digest(cases[case]) for case in case_ids},
        "fixture_sha256": {
            fixture: hashlib.sha256(fixture_text(fixture).encode()).hexdigest()
            for fixture in sorted({cases[case].fixture for case in case_ids})
        },
        "reference_sha256": _reference_digests(),
        "evaluation_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("runner.py", "grading.py", "comparison.py", "prompt_ladder.py")
        },
        "attempts": repeat * (2 * sum(len(step.cases) for step in steps) + len(case_ids)),
        "cohorts": cohorts,
    }


def _result(root: Path, cohort: dict[str, Any]) -> dict[str, Any]:
    directory = root / cohort["name"]
    args = cohort["args"]
    expected_ids = {args[index + 1] for index, arg in enumerate(args) if arg == "--case"}
    repeat = int(args[args.index("--repeat") + 1]) if "--repeat" in args else 1
    if cohort["mode"] == "production":
        runs = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
        if (
            not runs
            or expected_ids
            and (
                {run["case_id"] for run in runs} != expected_ids
                or any(sum(run["case_id"] == case for run in runs) != repeat for case in expected_ids)
            )
        ):
            raise ValueError("Production report is incomplete")
        counts = {
            "runs": len(runs),
            "passed": sum(run["passed"] for run in runs),
            "infrastructure_errors": sum(bool(run["error"]) for run in runs),
        }
        status = (
            "infrastructure error"
            if counts["infrastructure_errors"]
            else "pass"
            if counts["passed"] == counts["runs"]
            else "behavioral failure"
        )
        return {"status": status, "after": counts, "cases": runs}
    comparison = json.loads((directory / "comparison.json").read_text())
    if (
        not comparison["cases"]
        or expected_ids
        and (
            set(comparison["cases"]) != expected_ids
            or any(case[arm]["runs"] != repeat for case in comparison["cases"].values() for arm in ("before", "after"))
        )
    ):
        raise ValueError("Comparison report is incomplete")
    counts = {
        arm: {
            key: sum(case[arm][key] for case in comparison["cases"].values())
            for key in ("runs", "passed", "infrastructure_errors")
        }
        for arm in ("before", "after")
    }
    if any(counts[arm]["infrastructure_errors"] for arm in counts):
        status = "infrastructure error"
    elif counts["after"]["passed"] < counts["after"]["runs"]:
        status = "after behavioral failure"
    elif comparison["improved"]:
        status = "benefit reproduced"
    else:
        status = "benefit not reproduced"
    return {"status": status, **counts, "cases": comparison["cases"]}


def _write_summary(root: Path, audit: dict[str, Any]) -> None:
    (root / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# AI prompt ladder audit",
        "",
        f"Status: {audit['status']}. Planned attempts: {audit['plan']['attempts']}.",
        "",
        "Every attempt remains in its cohort report. Cost means and paired delta standard deviations are in the linked comparisons. Infrastructure failures are not replaced by retries.",
        "",
        "| Section | Mode | Before | After | Infrastructure | Outcome |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for result in audit["results"]:
        name = result["name"]
        before, after = result.get("before"), result.get("after")
        b = f"{before['passed']}/{before['runs']}" if before else "n/a"
        a = f"{after['passed']}/{after['runs']}" if after else "n/a"
        infra = sum(counts["infrastructure_errors"] for counts in (before, after) if counts)
        report = "summary.md" if result["mode"] == "production" else "comparison.md"
        link = f"[{name}]({name}/{report})" if after else f"[{name}](logs/{name}.log)"
        lines.append(f"| {link} | {result['mode']} | {b} | {a} | {infra} | {result['status']} |")
    (root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_audit(
    plan: dict[str, Any],
    root: Path,
    *,
    execute: Callable[..., Any] = subprocess.run,
    unchanged: Callable[[], bool] = lambda: True,
) -> int:
    """Run cohorts sequentially, retain failures, and stop if reports or inputs are unavailable."""
    root.mkdir(parents=True, exist_ok=False)
    (root / "logs").mkdir()
    (root / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    audit: dict[str, Any] = {"plan": plan, "status": "running", "results": [], "active": None}
    _write_summary(root, audit)
    try:
        for cohort in plan["cohorts"]:
            if not unchanged():
                audit["status"] = "incomplete: inputs changed"
                return 2
            audit["active"] = cohort["name"]
            _write_summary(root, audit)
            print(f"Running {cohort['name']} ({cohort['mode']})", flush=True)
            with (root / "logs" / f"{cohort['name']}.log").open("w", encoding="utf-8") as log:
                process = execute(
                    [sys.executable, "-m", "tests.ai_eval.runner", *cohort["args"]],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=Path(__file__).resolve().parents[2],
                )
            try:
                result = _result(root, cohort)
            except (OSError, ValueError, KeyError, TypeError):
                result = {"status": "incomplete report"}
            audit["results"].append(
                {"name": cohort["name"], "mode": cohort["mode"], "exit_code": process.returncode, **result}
            )
            if not unchanged():
                audit["status"] = "incomplete: inputs changed"
                return 2
            print(f"Finished {cohort['name']}: {result['status']} (exit {process.returncode})", flush=True)
            if result["status"] == "incomplete report" or process.returncode not in (0, 1):
                audit["status"] = "incomplete"
                return 2
            _write_summary(root, audit)
        clean = all(
            result["status"] in {"pass", "benefit reproduced"} and result["exit_code"] == 0
            for result in audit["results"]
        )
        audit["status"] = "pass" if clean else "completed with failures"
        return 0 if clean else 1
    finally:
        if audit["status"] == "running":
            audit["status"] = "interrupted"
        audit["active"] = None
        _write_summary(root, audit)
        print(f"Audit report: {root / 'summary.md'}", flush=True)
