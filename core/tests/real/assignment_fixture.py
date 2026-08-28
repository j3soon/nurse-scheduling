"""Serialize and replay complete schedule assignments."""

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
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from nurse_scheduling.constants import OFF
from nurse_scheduling.loader import load_data

ASSIGNMENT_FIXTURE_SCHEMA_VERSION = 1


def serialize_assignment_fixture(
    file_content: bytes,
    solution: Mapping[tuple[int, int, int], int],
    score: int,
) -> dict[str, Any]:
    """Return a portable fixture for a complete indexed scheduler solution."""
    scenario = load_data(file_content)
    start_date = scenario.dates.range.startDate
    n_days = (scenario.dates.range.endDate - start_date).days + 1
    n_shift_types = len(scenario.shiftTypes.items)
    n_people = len(scenario.people.items)
    expected_keys = {
        (day, shift_type, person)
        for day in range(n_days)
        for shift_type in range(n_shift_types)
        for person in range(n_people)
    }
    provided_keys = set(solution)
    if provided_keys != expected_keys:
        raise ValueError(
            "Solution keys must exactly match the scenario shift variables: "
            f"{len(expected_keys - provided_keys)} missing and "
            f"{len(provided_keys - expected_keys)} unexpected."
        )

    assignments = []
    for person, person_item in enumerate(scenario.people.items):
        shifts = []
        for day in range(n_days):
            selected_shift_types = []
            for shift_type in range(n_shift_types):
                value = solution[(day, shift_type, person)]
                if value not in (0, 1):
                    raise ValueError(f"Invalid solution value: {value}")
                if value == 1:
                    selected_shift_types.append(shift_type)
            if len(selected_shift_types) > 1:
                raise ValueError(f"Person index {person} has multiple shifts on day index {day}.")
            shifts.append(OFF if not selected_shift_types else scenario.shiftTypes.items[selected_shift_types[0]].id)
        assignments.append({"person": person_item.id, "shifts": shifts})

    return {
        "schemaVersion": ASSIGNMENT_FIXTURE_SCHEMA_VERSION,
        "scenarioSha256": hashlib.sha256(file_content).hexdigest(),
        "capturedScore": score,
        "dates": [str(start_date + timedelta(days=day)) for day in range(n_days)],
        "assignments": assignments,
    }


def deserialize_assignment_fixture(
    file_content: bytes,
    fixture: Mapping[str, Any],
) -> tuple[dict[tuple[int, int, int], int], int]:
    """Return a complete indexed solution and expected score from a fixture."""
    if fixture.get("schemaVersion") != ASSIGNMENT_FIXTURE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported assignment fixture schema version: {fixture.get('schemaVersion')!r}")
    scenario_sha256 = hashlib.sha256(file_content).hexdigest()
    if fixture.get("scenarioSha256") != scenario_sha256:
        raise ValueError("Assignment fixture does not match the scenario content.")

    scenario = load_data(file_content)
    start_date = scenario.dates.range.startDate
    n_days = (scenario.dates.range.endDate - start_date).days + 1
    expected_dates = [str(start_date + timedelta(days=day)) for day in range(n_days)]
    if fixture.get("dates") != expected_dates:
        raise ValueError("Assignment fixture dates do not match the scenario dates.")

    assignment_rows = fixture.get("assignments")
    if not isinstance(assignment_rows, list):
        raise TypeError("Assignment fixture assignments must be a list.")
    rows_by_person = {}
    for row in assignment_rows:
        if not isinstance(row, dict) or "person" not in row or "shifts" not in row:
            raise ValueError("Each assignment row must contain person and shifts.")
        person_id = row["person"]
        if person_id in rows_by_person:
            raise ValueError(f"Duplicate assignment row for person: {person_id!r}")
        rows_by_person[person_id] = row["shifts"]

    expected_people = {person.id for person in scenario.people.items}
    provided_people = set(rows_by_person)
    if provided_people != expected_people:
        raise ValueError(
            "Assignment fixture people must exactly match the scenario: "
            f"{len(expected_people - provided_people)} missing and "
            f"{len(provided_people - expected_people)} unexpected."
        )

    shift_type_indices = {shift_type.id: index for index, shift_type in enumerate(scenario.shiftTypes.items)}
    n_shift_types = len(shift_type_indices)
    solution = {
        (day, shift_type, person): 0
        for day in range(n_days)
        for shift_type in range(n_shift_types)
        for person in range(len(scenario.people.items))
    }
    for person, person_item in enumerate(scenario.people.items):
        shifts = rows_by_person[person_item.id]
        if not isinstance(shifts, list) or len(shifts) != n_days:
            raise ValueError(f"Assignment row for person {person_item.id!r} must contain {n_days} shifts.")
        for day, shift_type_id in enumerate(shifts):
            if shift_type_id == OFF:
                continue
            if shift_type_id not in shift_type_indices:
                raise ValueError(f"Unknown shift type in assignment fixture: {shift_type_id!r}")
            solution[(day, shift_type_indices[shift_type_id], person)] = 1

    expected_score = fixture.get("expectedScore", fixture.get("capturedScore"))
    if not isinstance(expected_score, int) or isinstance(expected_score, bool):
        raise TypeError("Assignment fixture score must be an integer.")
    return solution, expected_score
