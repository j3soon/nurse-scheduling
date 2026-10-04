"""Inspect compiled shift-request selectors and bounded counts from the current YAML."""

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
import hashlib
import json
import sys
from pathlib import Path

try:
    from .inspect_optimizer_result import _weight, _weight_arguments
except ImportError:
    from inspect_optimizer_result import _weight, _weight_arguments


def inspect_requests(context, source, *, weights=None, people=None, dates=None, max_requests=0):
    """Count selected nonzero-weight preference entries and expanded person/date targets."""
    if context.get("schema_version") != 1:
        raise ValueError("Unsupported compiled context")
    if context.get("source_sha256") != hashlib.sha256(source).hexdigest():
        raise ValueError("Compiled selectors are stale. Read the current YAML.")
    if not 0 <= max_requests <= 1000:
        raise ValueError("max_requests must be between 0 and 1000")
    ids = {str(p): p for p in context["people"]}
    if len(ids) != len(context["people"]):
        raise ValueError("Person IDs cannot be uniquely selected as text")
    if people and set(people) - ids.keys():
        raise ValueError("Unknown person ID")
    if dates and set(dates) - set(context["dates"]):
        raise ValueError("Unknown ISO date")
    selected_people = {ids[p] for p in people} if people else set(context["people"])
    selected_dates = set(dates) if dates else set(context["dates"])
    selected_weights = {_weight(w) for w in weights} if weights else None
    if selected_weights is not None and 0 in selected_weights:
        raise ValueError("Zero-weight entries are outside this context. Read the YAML.")
    entries, targets, rows = 0, 0, []
    for request in context["requests"]:
        if selected_weights is not None and _weight(request["weight"]) not in selected_weights:
            continue
        ps = [p for p in request["people"] if p in selected_people]
        ds = [d for d in request["dates"] if d in selected_dates]
        if not ps or not ds:
            continue
        entries += 1
        targets += len(ps) * len(ds)
        if len(rows) < max_requests:
            rows.append({**request, "people": ps, "dates": ds})
    return {
        "source_sha256": context["source_sha256"],
        "scope": "Resolved nonzero shift requests. Targets are counted per preference entry. Staffing and succession feasibility are outside this inspection.",
        "request_entries": entries,
        "person_date_targets": targets,
        "requests": rows,
        "requests_truncated": entries > len(rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, default=Path("/workspace/schedule-context.json"))
    parser.add_argument("--source", type=Path, default=Path("/workspace/schedule.yaml"))
    parser.add_argument(
        "--weight",
        action="append",
        help="Numeric weight, repeatable. Use --weight=-.inf for bans.",
    )
    parser.add_argument("--person", action="append", help="Exact person ID, repeatable.")
    parser.add_argument("--date", action="append", help="ISO date, repeatable.")
    parser.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="Returned preference entry limit. Defaults to 0 for counts only.",
    )
    args = parser.parse_args(_weight_arguments(sys.argv[1:]))
    try:
        result = inspect_requests(
            json.loads(args.context.read_text()),
            args.source.read_bytes(),
            weights=args.weight,
            people=args.person,
            dates=args.date,
            max_requests=args.max_requests,
        )
    except (ValueError, FileNotFoundError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
