"""Canonical request selectors for sandbox optimizer-result inspection."""

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

import hashlib
import math
from typing import Any

from nurse_scheduling.constants import OFF, OFF_sid
from nurse_scheduling.loader import load_data
from nurse_scheduling.models import CompiledShiftRequest


def build_result_context(schedule_yaml: str) -> dict[str, Any]:
    """Project canonical selectors into a portable result-reader context."""
    data = load_data(schedule_yaml.encode())
    compiled = data.compiled_schedule
    people = [person.id for person in data.people.items]
    shifts = [shift.id for shift in data.shiftTypes.items]
    dates = [date.isoformat() for date in compiled.dates]
    requests = []
    for index, (pref, resolved) in enumerate(zip(data.preferences, compiled.preferences, strict=True)):
        if not isinstance(resolved, CompiledShiftRequest) or pref.weight == 0:
            continue
        weight = pref.weight
        if isinstance(weight, float) and math.isinf(weight):
            weight = ".inf" if weight > 0 else "-.inf"
        requests.append(
            {
                "preference_index": index,
                "weight": weight,
                "people": [people[p] for p in resolved.people],
                "dates": [dates[d] for d in resolved.dates],
                "shift_types": [OFF if s == OFF_sid else shifts[s] for s in resolved.shift_types],
            }
        )
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(schedule_yaml.encode()).hexdigest(),
        "people": people,
        "dates": dates,
        "shift_types": shifts,
        "requests": requests,
    }
