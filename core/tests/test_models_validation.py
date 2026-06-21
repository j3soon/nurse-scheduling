"""Validation-focused tests for Pydantic scheduling models."""

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

import datetime
import os
import sys

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.models import NurseSchedulingData


def _base_payload() -> dict:
    return {
        "apiVersion": "alpha",
        "dates": {"range": {"startDate": datetime.date(2025, 1, 1), "endDate": datetime.date(2025, 1, 1)}},
        "people": {"items": [{"id": "n1"}]},
        "shiftTypes": {"items": [{"id": "D"}]},
        "preferences": [
            {"type": "at most one shift per day"},
            {"type": "shift type requirement", "shiftType": "D", "requiredNumPeople": 1},
        ],
    }


def test_model_requires_at_most_one_shift_preference():
    payload = _base_payload()
    payload["preferences"] = [payload["preferences"][1]]

    with pytest.raises(ValueError, match="Missing required preferences"):
        NurseSchedulingData.model_validate(payload)


def test_model_accepts_nested_shift_type_requirement_groups():
    payload = _base_payload()
    payload["shiftTypes"]["items"] = [{"id": "D"}, {"id": "E"}]
    payload["preferences"][1]["shiftType"] = [["D", "E"]]
    payload["preferences"][1]["shiftTypeCoefficients"] = [["D", 2]]

    data = NurseSchedulingData.model_validate(payload)

    assert data.preferences[1].shiftType == [["D", "E"]]
    assert data.preferences[1].shiftTypeCoefficients == [("D", 2)]


def test_model_accepts_zero_float_weight():
    payload = _base_payload()
    payload["preferences"].append(
        {"type": "shift request", "person": "n1", "date": "2025-01-01", "shiftType": "D", "weight": 0}
    )

    data = NurseSchedulingData.model_validate(payload)

    assert data.preferences[2].weight == 0


def test_model_rejects_invalid_date_range():
    payload = _base_payload()
    payload["dates"]["range"]["startDate"] = datetime.date(2025, 1, 2)
    payload["dates"]["range"]["endDate"] = datetime.date(2025, 1, 1)

    with pytest.raises(ValueError, match="enddate must be after or equal to startdate"):
        NurseSchedulingData.model_validate(payload)


def test_model_rejects_duplicate_or_reserved_shift_type_ids():
    payload = _base_payload()
    payload["shiftTypes"]["items"] = [{"id": "D"}, {"id": "D"}]
    with pytest.raises(ValueError, match="Duplicated shift type ID: 'D'"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["shiftTypes"]["items"] = [{"id": "ALL"}]
    payload["preferences"][1]["shiftType"] = "ALL"
    with pytest.raises(ValueError, match="Shift type ID 'ALL' cannot be one of the reserved values"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["shiftTypes"]["groups"] = [{"id": "D", "members": ["D"]}]
    with pytest.raises(ValueError, match="Duplicated shift type group .*'D'"):
        NurseSchedulingData.model_validate(payload)


def test_model_rejects_duplicate_or_reserved_people_ids():
    payload = _base_payload()
    payload["people"]["items"] = [{"id": "n1"}, {"id": "n1"}]
    with pytest.raises(ValueError, match="Duplicated person ID: 'n1'"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["people"]["items"] = [{"id": "ALL"}]
    with pytest.raises(ValueError, match="Person ID 'ALL' cannot be one of the reserved values"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["people"]["groups"] = [{"id": "n1", "members": ["n1"]}]
    with pytest.raises(ValueError, match="Duplicated people group .*'n1'"):
        NurseSchedulingData.model_validate(payload)


def test_model_rejects_invalid_dates_items_and_group_ids():
    payload = _base_payload()
    payload["dates"]["items"] = [datetime.date(2025, 1, 1)]
    with pytest.raises(ValueError, match="dates.items is not allowed"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["dates"]["groups"] = [{"id": "g1", "members": ["2025-01-01"]}, {"id": "g1", "members": ["2025-01-01"]}]
    with pytest.raises(ValueError, match="Duplicated date group ID: 'g1'"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["dates"]["groups"] = [{"id": "WEEKDAY", "members": ["2025-01-01"]}]
    with pytest.raises(ValueError, match="Date group ID 'WEEKDAY' cannot be one of the reserved values"):
        NurseSchedulingData.model_validate(payload)

    payload = _base_payload()
    payload["dates"]["groups"] = [{"id": "2025-01-01", "members": ["2025-01-01"]}]
    with pytest.raises(ValueError, match="Date group ID '2025-01-01' must not be in the format"):
        NurseSchedulingData.model_validate(payload)
