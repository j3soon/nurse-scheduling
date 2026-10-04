"""Summarize resolved nonzero shift requests by numeric weight.

Counts are per preference entry and per expanded person/date target, including overlaps.
"""

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
from pathlib import Path

try:
    from .inspect_optimizer_result import _weight
    from .inspect_shift_requests import inspect_requests
except ImportError:
    from inspect_optimizer_result import _weight
    from inspect_shift_requests import inspect_requests


def inspect_tiers(context, source, *, max_tiers=100):
    """Return complete per-weight counts without returning individual requests."""
    if max_tiers <= 0:
        raise ValueError("max_tiers must be positive")
    max_tiers = min(max_tiers, 100)
    totals = inspect_requests(context, source)
    weights = {_weight(row["weight"]): row["weight"] for row in context["requests"]}
    tiers = []
    for weight, value in sorted(weights.items())[:max_tiers]:
        counts = inspect_requests(context, source, weights=[str(weight)])
        tiers.append(
            {
                "weight": value,
                "request_entries": counts["request_entries"],
                "person_date_targets": counts["person_date_targets"],
            }
        )
    return {
        "source_sha256": totals["source_sha256"],
        "scope": totals["scope"],
        "request_entries": totals["request_entries"],
        "person_date_targets": totals["person_date_targets"],
        "tier_count": len(weights),
        "tiers": tiers,
        "tiers_truncated": len(tiers) < len(weights),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, default=Path("/workspace/schedule-context.json"))
    parser.add_argument("--source", type=Path, default=Path("/workspace/schedule.yaml"))
    parser.add_argument("--max-tiers", type=int, default=100, help="Returned weight-tier limit, at most 100.")
    args = parser.parse_args()
    try:
        result = inspect_tiers(
            json.loads(args.context.read_text(encoding="utf-8")), args.source.read_bytes(), max_tiers=args.max_tiers
        )
    except (ValueError, FileNotFoundError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
