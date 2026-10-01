"""Inspect optimizer assignments and signed requests without parsing annotations as shifts."""

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

# This file is mostly AI generated.

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

try:
    from .inspect_xlsx import _check_archive
except ImportError:  # Standalone copy in /reference/tools.
    from inspect_xlsx import _check_archive

RESULT = "/workspace/optimizer-results/optimized-schedule.xlsx"
CONTEXT = "/workspace/optimizer-results/schedule-context.json"
MAX_CELLS = 1_000_000


def _weight(value: Any) -> Decimal:
    if value == ".inf":
        return Decimal("Infinity")
    if value == "-.inf":
        return Decimal("-Infinity")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"Invalid numeric request weight: {value}") from error
    if result.is_nan():
        raise ValueError("NaN is not a request weight")
    return result


def _assigned(value: Any, shift_types: list[str]) -> str:
    text = "" if value is None else str(value)
    annotations = r"(?:\s*\[[^\]]*\])*\s*"
    candidates = []
    if re.fullmatch(annotations, text):
        candidates.append("OFF")
    for shift in shift_types:
        if text.startswith(shift) and re.fullmatch(annotations, text[len(shift) :]):
            candidates.append(shift)
    if len(candidates) != 1:
        raise ValueError(f"Assignment is unknown or ambiguous: {value!r}")
    return candidates[0]


def _date_columns(row, dates: list[str]) -> dict[str, int] | None:
    columns = {}
    for date in dates:
        year, month, day = map(int, date.split("-"))
        # The exporter uses day, month/day, or year/month/day according to range.
        labels = {date, str(day), f"{month}/{day}", f"{year}/{month}/{day}"}
        matches = [col for col, cell in enumerate(row) if str(cell.value) in labels]
        if len(matches) != 1:
            return None
        columns[date] = matches[0]
    return columns if len(set(columns.values())) == len(dates) else None


def _read_assignments(path: Path, context: dict) -> tuple[dict, Any, Any]:
    _check_archive(path)
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        candidates = []
        for sheet in workbook:
            if sheet.max_row * sheet.max_column > MAX_CELLS:
                raise ValueError("Optimizer worksheet is too large")
            rows = list(sheet.iter_rows())
            people = set(context["people"])
            for header, row in enumerate(rows[:10]):
                columns = _date_columns(row, context["dates"])
                if columns is None:
                    continue
                assigned = {}
                last_person_row = header
                for row_index, cells in enumerate(rows[header + 1 :], header + 1):
                    person = cells[0].value
                    if person not in people:
                        continue
                    if person in assigned:
                        raise ValueError(f"Duplicate person row: {person}")
                    assigned[person] = {}
                    for date, col in columns.items():
                        cell = cells[col]
                        if cell.data_type == "f":
                            raise ValueError("Formula assignments are not supported")
                        assigned[person][date] = _assigned(cell.value, context["shift_types"])
                    last_person_row = row_index
                    if set(assigned) == people:
                        break
                if set(assigned) != people:
                    continue
                metadata = {}
                for cells in rows[last_person_row + 1 :]:
                    if cells[0].value in {"Score", "Status"}:
                        values = [c.value for c in cells[1:] if c.value is not None]
                        if len(values) == 1:
                            metadata[cells[0].value] = values[0]
                candidates.append((assigned, metadata.get("Score"), metadata.get("Status")))
        if len(candidates) != 1:
            raise ValueError("Could not uniquely locate the optimizer roster and date headers")
        return candidates[0]
    finally:
        workbook.close()


def inspect_result(
    path: Path, context: dict, source_sha256: str, weights: list[str] | None = None, max_unmet: int = 20
) -> dict:
    """Audit nonzero-weight person/date requests, independently of export markers."""
    if context.get("schema_version") != 1 or context.get("source_sha256") != source_sha256:
        raise ValueError("The compiled context does not match the optimizer source")
    if max_unmet < 0:
        raise ValueError("max_unmet must not be negative")
    assignments, score, status = _read_assignments(path, context)
    selected = {_weight(w) for w in weights} if weights else None
    summary = {}
    unmet = []
    for request in context["requests"]:
        weight = _weight(request["weight"])
        if selected is not None and weight not in selected:
            continue
        row = summary.setdefault(weight, {"weight": request["weight"], "total": 0, "satisfied": 0, "unmet": 0})
        for person in request["people"]:
            for date in request["dates"]:
                assigned = assignments[person][date]
                matches = assigned in request["shift_types"]
                satisfied = matches if weight > 0 else not matches
                row["total"] += 1
                row["satisfied" if satisfied else "unmet"] += 1
                if not satisfied:
                    unmet.append(
                        {
                            "preference_index": request["preference_index"],
                            "person": person,
                            "date": date,
                            "requested": request["shift_types"],
                            "assigned": assigned,
                            "weight": request["weight"],
                        }
                    )
    return {
        "source_sha256": source_sha256,
        "score": score,
        "score_direction": "maximize",
        "status": status,
        "summary": list(summary.values()),
        "unmet": unmet[:max_unmet],
        "unmet_truncated": len(unmet) > max_unmet,
    }


def _weight_arguments(arguments: list[str]) -> list[str]:
    """Keep negative numeric weights from being mistaken for option names."""
    normalized = []
    index = 0
    while index < len(arguments):
        if arguments[index] == "--weight" and index + 1 < len(arguments):
            value = arguments[index + 1]
            try:
                _weight(value)
            except ValueError:
                pass
            else:
                normalized.append(f"--weight={value}")
                index += 2
                continue
        normalized.append(arguments[index])
        index += 1
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit an optimizer workbook using canonical compiled request selectors."
    )
    parser.add_argument("workbook", nargs="?", type=Path, default=Path(RESULT))
    parser.add_argument("--context", type=Path, default=Path(CONTEXT))
    parser.add_argument("--source-sha256", required=True, help="source_sha256 from the optimizer completion")
    parser.add_argument(
        "--weight", action="append", help="numeric request weight, repeatable. Use --weight=-.inf for bans"
    )
    parser.add_argument("--max-unmet", type=int, default=20)
    args = parser.parse_args(_weight_arguments(sys.argv[1:]))
    try:
        result = inspect_result(
            args.workbook, json.loads(args.context.read_text()), args.source_sha256, args.weight, args.max_unmet
        )
    except (ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
