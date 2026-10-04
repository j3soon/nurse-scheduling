"""Audit staffing and succession preferences against a concrete assignment."""

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

import math
from collections.abc import Mapping

from .constants import OFF_sid
from .models import (
    CompiledShiftTypeRequirements,
    CompiledShiftTypeSuccessions,
    NurseSchedulingData,
)
from .preference_types import iter_succession_patterns, staffing_expression


def _weight(value):
    return (".inf" if value > 0 else "-.inf") if isinstance(value, float) and math.isinf(value) else value


def audit_staffing_and_successions(data: NurseSchedulingData, assignments: Mapping[tuple[int, int], int]) -> dict:
    """Count policy misses using the optimizer's compiled selectors and windows.

    Assignment keys are (day, person), with OFF represented by OFF_sid.
    This audits only staffing requirements and shift successions.
    """
    compiled = data.compiled_schedule
    expected = {(d, p) for d in range(len(compiled.dates)) for p in range(len(data.people.items))}
    if assignments.keys() != expected:
        raise ValueError("Audit requires one assignment for every person and date")
    valid = {OFF_sid, *range(len(data.shiftTypes.items))}
    if any(s not in valid for s in assignments.values()):
        raise ValueError("Unknown assigned shift")
    staffing, successions = [], []
    for index, (pref, resolved) in enumerate(zip(data.preferences, compiled.preferences, strict=True)):
        if isinstance(resolved, CompiledShiftTypeRequirements):
            row = {
                "preference_index": index,
                "weight": _weight(pref.weight),
                "checks": 0,
                "hard_unmet": 0,
                "preferred_unmet": 0,
                "preferred_shortfall": 0,
            }
            for d in resolved.dates:
                for group in resolved.shift_type_groups:
                    actual = staffing_expression(
                        lambda d, s, p: int(assignments[d, p] == s),
                        len(data.people.items),
                        resolved,
                        d,
                        group,
                    )
                    eligible = resolved.qualified_people
                    unqualified = eligible is not None and any(
                        assignments[d, p] in group for p in range(len(data.people.items)) if p not in eligible
                    )
                    if pref.preferredNumPeople is None:
                        hard_unmet = actual != pref.requiredNumPeople
                    else:
                        hard_unmet = not pref.requiredNumPeople <= actual <= pref.preferredNumPeople
                        shortfall = max(0, pref.preferredNumPeople - actual)
                        row["preferred_unmet"] += int(shortfall > 0)
                        row["preferred_shortfall"] += shortfall
                    row["checks"] += 1
                    row["hard_unmet"] += int(hard_unmet or unqualified)
            staffing.append(row)
        elif isinstance(resolved, CompiledShiftTypeSuccessions) and pref.weight != 0:
            row = {
                "preference_index": index,
                "weight": _weight(pref.weight),
                "windows": 0,
                "goal": "avoid_pattern" if pref.weight < 0 else "match_pattern",
                "satisfied": 0,
                "unmet": 0,
            }
            for p, d, _pattern_index, pattern in iter_succession_patterns(
                resolved, compiled.histories, len(compiled.dates)
            ):
                matches = all(
                    assignments[d + i, p] != OFF_sid
                    if element.matches_all_working_shifts
                    else assignments[d + i, p] in element.shift_types
                    for i, element in enumerate(pattern)
                )
                row["windows"] += 1
                satisfied = matches if pref.weight > 0 else not matches
                row["satisfied"] += int(satisfied)
                row["unmet"] += int(not satisfied)
            successions.append(row)
    return {"staffing": staffing, "successions": successions}
