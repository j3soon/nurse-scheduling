"""Summarize matched evaluation costs without counting failures as savings."""

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

import math
import statistics
from collections.abc import Sequence
from typing import Any

METRICS = (
    "prompt_tokens",
    "cached_prompt_tokens",
    "uncached_prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "total_tokens",
    "tool_calls",
    "reads",
    "bash_calls",
    "turns",
    "seconds",
)


def _metric(record: dict[str, Any], name: str) -> float | None:
    if name.endswith("tokens"):
        usage = record.get("token_usage") or {}
        if not usage.get("available") or not usage.get("complete"):
            return None
        value = usage.get(name)
        if name == "uncached_prompt_tokens":
            prompt, cached = usage.get("prompt_tokens"), usage.get("cached_prompt_tokens")
            value = prompt - cached if prompt is not None and cached is not None else None
    elif name in ("tool_calls", "reads", "bash_calls"):
        tools = record.get("tools")
        if tools is None:
            return None
        # Failed calls still consume work and belong in the count.
        tool_names = [tool.removesuffix("(failed)") for tool in tools]
        value = len(tools) if name == "tool_calls" else tool_names.count("read" if name == "reads" else "bash")
    else:
        value = record.get(name)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "mean": statistics.mean(values) if values else None,
        "std": statistics.stdev(values) if len(values) > 1 else None,
    }


def _index(records: Sequence[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    indexed = {}
    for record in records:
        key = (record["case_id"], record.get("repetition", 1))
        if key in indexed:
            raise ValueError(f"Duplicate case/repetition in comparison: {key}")
        indexed[key] = record
    return indexed


def comparison_statistics(before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pair by case and repetition, retaining reliability on every attempt."""
    before_index, after_index = _index(before), _index(after)
    cases = {}
    for case_id in sorted({key[0] for key in before_index} | {key[0] for key in after_index}):
        arms = [[record for record in records if record["case_id"] == case_id] for records in (before, after)]
        reliability = [
            {
                "runs": len(records),
                "passed": sum(bool(record["passed"]) for record in records),
                "pass_rate": sum(bool(record["passed"]) for record in records) / len(records) if records else None,
                "infrastructure_errors": sum(bool(record.get("error")) for record in records),
            }
            for records in arms
        ]
        keys = sorted(key for key in before_index.keys() & after_index.keys() if key[0] == case_id)
        passing = [
            (before_index[key], after_index[key])
            for key in keys
            if all(record["passed"] and not record.get("error") for record in (before_index[key], after_index[key]))
        ]
        metrics = {}
        for name in METRICS:
            values = [(_metric(left, name), _metric(right, name)) for left, right in passing]
            complete = [(left, right) for left, right in values if left is not None and right is not None]
            left_stats = _distribution([left for left, _ in complete])
            right_stats = _distribution([right for _, right in complete])
            metrics[name] = {
                "pairs": len(complete),
                "missing_pairs": len(passing) - len(complete),
                "before": left_stats,
                "after": right_stats,
                "delta": _distribution([right - left for left, right in complete]),
                "relative_delta": right_stats["mean"] / left_stats["mean"] - 1 if left_stats["mean"] else None,
            }
        cases[case_id] = {
            "before": reliability[0],
            "after": reliability[1],
            "pass_rate_delta": reliability[1]["pass_rate"] - reliability[0]["pass_rate"]
            if all(arm["runs"] for arm in reliability)
            else None,
            "matched_pairs": len(keys),
            "passing_pairs": len(passing),
            "unmatched_before": len(arms[0]) - len(keys),
            "unmatched_after": len(arms[1]) - len(keys),
            "metrics": metrics,
        }
    return {"schema_version": 1, "cases": cases}


def _format(distribution: dict[str, float | None], *, delta: bool = False) -> str:
    mean, std = distribution["mean"], distribution["std"]
    if mean is None:
        return "n/a"
    value = f"{mean:+.1f}" if delta else f"{mean:.1f}"
    return f"{value} ± {std:.1f}" if std is not None else f"{value} (SD n/a)"


def comparison_metrics_markdown(summary: dict[str, Any]) -> str:
    """Always report measured metrics, independent of the selected benefit gate."""
    lines = [
        "## Matched cost metrics",
        "",
        "Means and sample standard deviations use repetitions where both arms pass without infrastructure errors.",
        "Pairs is usable/matched repetitions. Incomplete token telemetry is excluded, never replaced with zero.",
        "Delta is after minus before. Delta SD is computed from paired differences, not from the arm SDs.",
        "Reported reasoning tokens are part of completion tokens and must not be added again.",
        "Small samples describe these runs and do not establish statistical significance.",
        "",
        "| Case | Metric | Pairs | Before mean ± SD | After mean ± SD | Delta mean ± SD | Change |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    unmatched = []
    for case_id, case in summary["cases"].items():
        for name, metric in case["metrics"].items():
            change = f"{metric['relative_delta']:+.1%}" if metric["relative_delta"] is not None else "n/a"
            lines.append(
                f"| {case_id} | {name} | {metric['pairs']}/{case['matched_pairs']} "
                f"| {_format(metric['before'])} | {_format(metric['after'])} "
                f"| {_format(metric['delta'], delta=True)} | {change} |"
            )
        if case["unmatched_before"] or case["unmatched_after"]:
            unmatched.append(
                f"{case_id}: unmatched repetitions excluded: before {case['unmatched_before']}, after {case['unmatched_after']}."
            )
    if unmatched:
        lines.extend(["", *unmatched])
    return "\n".join(lines)
