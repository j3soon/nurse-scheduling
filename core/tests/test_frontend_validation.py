"""Tests for the web frontend Pydantic validation subset."""

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

from copy import deepcopy

import pytest
from pydantic import ValidationError

from nurse_scheduling.frontend_validation import load_frontend_data, validate_frontend_data
from nurse_scheduling.models import NurseSchedulingData


def _base_payload() -> dict:
    return {
        "appVersion": "v0.0.0-test",
        "apiVersion": "alpha",
        "description": "",
        "dates": {
            "range": {"startDate": "2026-01-01", "endDate": "2026-01-02"},
            "items": [],
            "groups": [{"id": "FIRST", "description": "", "members": ["2026-01-01"]}],
        },
        "people": {
            "items": [
                {"id": "P1", "description": "", "history": []},
                {"id": "P2", "description": "", "history": []},
            ],
            "groups": [{"id": "PEOPLE", "description": "", "members": ["P1", "P2"]}],
        },
        "shiftTypes": {
            "items": [{"id": "D", "description": ""}, {"id": "N", "description": ""}],
            "groups": [{"id": "WORK", "description": "", "members": ["D", "N"]}],
        },
        "preferences": [
            {"type": "at most one shift per day"},
            {
                "type": "shift request",
                "person": ["P1"],
                "date": ["FIRST"],
                "shiftType": ["D"],
                "weight": 1,
            },
        ],
        "export": {"formatting": [], "extraColumns": [], "extraRows": []},
    }


def _model(payload: dict | None = None) -> NurseSchedulingData:
    return NurseSchedulingData.model_validate(payload or _base_payload())


def test_frontend_model_accepts_frontend_generated_shape():
    result = validate_frontend_data(_model())

    assert result.apiVersion == "alpha"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["preferences"].append(
                {
                    "type": "shift type requirement",
                    "shiftType": [["D", "N"]],
                    "qualifiedPeople": ["P1"],
                    "date": ["ALL"],
                    "requiredNumPeople": 1,
                }
            ),
            "must not contain nested references",
        ),
        (
            lambda payload: payload["preferences"].append(
                {
                    "type": "shift count",
                    "person": ["P1"],
                    "countDates": ["ALL"],
                    "countShiftTypes": ["D"],
                    "expression": ["x >= T", "x <= T"],
                    "target": [1, 2],
                }
            ),
            "expression must be a scalar",
        ),
    ],
)
def test_frontend_model_rejects_backend_only_shapes(mutate, message):
    payload = deepcopy(_base_payload())
    mutate(payload)
    model = _model(payload)

    with pytest.raises(ValidationError, match=message):
        validate_frontend_data(model)


def test_frontend_model_rejects_numeric_ids_and_scalar_references():
    payload = _base_payload()
    payload["people"]["items"][0]["id"] = 1
    payload["people"]["groups"][0]["members"][0] = 1
    payload["preferences"][1]["person"] = 1
    model = _model(payload)

    with pytest.raises(ValidationError, match=r"people.items\[0\].id must be a string"):
        validate_frontend_data(model)


def test_load_frontend_data_runs_yaml_backend_and_frontend_validation():
    content = b"""
apiVersion: alpha
dates:
  range: {startDate: 2026-01-01, endDate: 2026-01-01}
people:
  items: [{id: 1, description: ""}]
shiftTypes:
  items: [{id: D, description: ""}]
preferences:
  - type: at most one shift per day
"""

    with pytest.raises(ValidationError, match="must be a string for the web frontend"):
        load_frontend_data(content)
