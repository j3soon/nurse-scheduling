"""Validate completed evaluation reports before adding more repetitions."""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SavedReport:
    directory: Path
    metadata: dict[str, Any]
    records: list[dict[str, Any]]
    counts: dict[str, int]


@dataclass
class ReportExtension:
    reports: dict[str, SavedReport]
    metadata: dict[str, dict[str, Any]]
    starts: dict[str, int]
    trajectories: list[tuple[dict[str, Any], dict[str, Any]]]


def read_completed_reports(root: Path) -> dict[str, SavedReport]:
    """Require complete, uniquely numbered attempts in every saved arm."""
    progress = json.loads((root / "progress.json").read_text(encoding="utf-8"))
    if progress["status"] != "complete":
        raise ValueError("Only completed reports can be extended")
    paired = (root / "before").exists() or (root / "after").exists()
    directories = [root / "before", root / "after"] if paired else [root]
    reports = {}
    for directory in directories:
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        records = [json.loads(line) for line in (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        if not records:
            raise ValueError("Saved report has no attempts")
        label = directory.name if paired else records[0]["prompt_variant"]
        ids = metadata["case_ids"]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Saved report has invalid case IDs")
        counts = metadata.get("repetitions_by_case", dict.fromkeys(ids, metadata["repetitions"]))
        if set(counts) != set(ids) or any(type(n) is not int or n <= 0 for n in counts.values()):
            raise ValueError("Saved report has invalid repetition counts")
        keys = [(row["case_id"], row["repetition"]) for row in records]
        expected = {(case_id, n) for case_id, count in counts.items() for n in range(1, count + 1)}
        if len(set(keys)) != len(keys) or set(keys) != expected:
            raise ValueError("Saved report has duplicate, missing or unexpected repetitions")
        if any(row["prompt_variant"] != label for row in records):
            raise ValueError("Saved report mixes prompt variants")
        reports[label] = SavedReport(directory, metadata, records, counts)
    first = next(iter(reports.values()))
    if any(r.metadata["case_ids"] != first.metadata["case_ids"] or r.counts != first.counts for r in reports.values()):
        raise ValueError("Saved comparison arms have different cases or repetitions")
    total = sum(len(r.records) for r in reports.values())
    if progress["completed"] != total or progress["expected"] != total:
        raise ValueError("Saved progress does not match completed attempts")
    return reports


def prepare_extension(
    reports: dict[str, SavedReport],
    current: dict[str, dict[str, Any]],
    selected_ids: list[str],
    repetitions: int,
    source: Path,
) -> ReportExtension:
    """Check measured inputs, preserve old attempts and allocate only missing runs."""
    if set(reports) != set(current):
        raise ValueError("Reuse the original prompt comparison flags when extending a comparison")
    first = next(iter(reports.values()))
    if set(selected_ids) - first.counts.keys():
        raise ValueError("Selected cases are outside the saved report")
    if any(repetitions < first.counts[case_id] for case_id in selected_ids):
        raise ValueError("--repeat cannot remove saved attempts")
    starts = {case_id: first.counts[case_id] + 1 for case_id in selected_ids if repetitions > first.counts[case_id]}
    if not starts:
        raise ValueError("--repeat must add at least one repetition")
    fingerprint_keys = (
        "provider_model",
        "fail_fast",
        "sandbox_configuration",
        "case_ids",
        "cases_sha256",
        "prompt_sha256",
        "references_sha256",
        "fixtures_sha256",
        "attachments_sha256",
    )
    metadata = {}
    trajectories = []
    for label, report in reports.items():
        for key in fingerprint_keys:
            if key not in report.metadata or report.metadata[key] != current[label][key]:
                raise ValueError(f"Saved {label} report has changed {key}. Run a new comparison.")
        counts = {**report.counts, **dict.fromkeys(starts, repetitions)}
        metadata[label] = {
            **report.metadata,
            "repetitions": max(counts.values()),
            "repetitions_by_case": counts,
            "extensions": [
                *report.metadata.get("extensions", []),
                {
                    "source_report": str(source.resolve()),
                    "git_revision": current[label]["git_revision"],
                    "dirty_diff_sha256": current[label]["dirty_diff_sha256"],
                    "first_repetitions": starts,
                    "last_repetition": repetitions,
                },
            ],
        }
        for record in report.records:
            case_id, repetition = record["case_id"], record["repetition"]
            suffix = f"--run-{repetition}" if report.metadata["repetitions"] > 1 else ""
            path = report.directory / "cases" / f"{case_id}{suffix}.json"
            detail = json.loads(path.read_text(encoding="utf-8"))
            if any(key not in detail or detail[key] != value for key, value in record.items()):
                raise ValueError(f"Saved trajectory differs from its result: {case_id}#{repetition}")
            trajectories.append((record, detail))
    return ReportExtension(reports, metadata, starts, trajectories)
