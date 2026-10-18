"""Build date groups from the application's bundled Taiwan holiday calendar."""

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
from datetime import date, timedelta
from pathlib import Path

from ruamel.yaml import YAML, YAMLError


def load_calendar(path: Path) -> tuple[date, date, dict[date, bool]]:
    """Read the maintained frontend table without executing TypeScript."""
    source = path.read_text(encoding="utf-8")
    bounds = dict(re.findall(r"export const TAIWAN_HOLIDAY_SUPPORTED_(START|END) = '(\d{4}-\d{2}-\d{2})';", source))
    block = re.search(r"const SPECIAL_DATE_INFO: TaiwanSpecialDateInfo\[\] = \[(.*?)\n\];", source, re.DOTALL)
    if set(bounds) != {"START", "END"} or block is None:
        raise ValueError("Unsupported bundled calendar format")
    start, end = date.fromisoformat(bounds["START"]), date.fromisoformat(bounds["END"])
    special = {}
    for line in block[1].splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        row = re.fullmatch(r"\['(\d{4}-\d{2}-\d{2})', '(?:[^'\\]|\\.)*', (true|false)\],?", line)
        if row is None:
            raise ValueError("Unsupported bundled calendar row")
        day = date.fromisoformat(row[1])
        if day in special or not start <= day <= end:
            raise ValueError("Duplicate or out-of-range calendar date")
        special[day] = row[2] == "true"
    if not special:
        raise ValueError("The bundled calendar has no special dates")
    return start, end, special


def build_groups(schedule: dict, calendar: Path, *, start: str | None = None, end: str | None = None) -> dict:
    """Return replacement groups while preserving every unrelated group."""
    if (start is None) != (end is None):
        raise ValueError("Provide both --start and --end")
    current = schedule["dates"]
    first = date.fromisoformat(str(start or current["range"]["startDate"]))
    last = date.fromisoformat(str(end or current["range"]["endDate"]))
    supported_start, supported_end, special = load_calendar(calendar)
    if not supported_start <= first <= last <= supported_end:
        raise ValueError(f"The bundled calendar supports {supported_start} through {supported_end}")
    groups = [group for group in current.get("groups", []) if group["id"] not in {"WORKDAY", "FREEDAY"}]
    workdays, freedays = [], []
    # Match the frontend's generated date IDs: DD, MM-DD, or YYYY-MM-DD.
    date_format = (
        "%d"
        if (first.year, first.month) == (last.year, last.month)
        else "%m-%d"
        if first.year == last.year
        else "%Y-%m-%d"
    )
    day = first
    while day <= last:
        (freedays if special.get(day, day.weekday() >= 5) else workdays).append(day.strftime(date_format))
        day += timedelta(days=1)
    groups.extend(
        [
            {
                "id": "WORKDAY",
                "description": "Taiwan workdays imported from the current holiday calendar",
                "members": workdays,
            },
            {
                "id": "FREEDAY",
                "description": "Taiwan freedays imported from the current holiday calendar",
                "members": freedays,
            },
        ]
    )
    return {"range": {"startDate": first.isoformat(), "endDate": last.isoformat()}, "groups": groups}


def main():
    parser = argparse.ArgumentParser(
        description="Generate Taiwan calendar groups as JSON. Preserves custom groups and does not edit files."
    )
    parser.add_argument("schedule", nargs="?", type=Path, default=Path("/workspace/schedule.yaml"))
    parser.add_argument("--calendar", type=Path, default=Path("/reference/taiwanHolidays.ts"))
    parser.add_argument("--start", help="New start date YYYY-MM-DD. Requires --end.")
    parser.add_argument("--end", help="New end date YYYY-MM-DD. Requires --start.")
    args = parser.parse_args()
    try:
        schedule = YAML(typ="safe").load(args.schedule.read_text(encoding="utf-8"))
        result = build_groups(schedule, args.calendar, start=args.start, end=args.end)
    except (ValueError, KeyError, TypeError, OSError, YAMLError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
