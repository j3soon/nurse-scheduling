"""Error-path tests for preference handler validation logic."""

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

import os
import sys
from types import SimpleNamespace
import datetime
import logging

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import preference_types, scheduler
from nurse_scheduling.models import ShiftTypeSuccessionsPreference, ShiftAffinityPreference


def test_shift_type_requirements_rejects_inf_weight_with_preferred_num_people():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 0
    preferredNumPeople: 1
    weight: .inf
"""
    with pytest.raises(ValueError, match="Infinity weights are not allowed"):
        scheduler.schedule(yaml_content)


def test_shift_count_rejects_mismatched_expression_and_target_lengths():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: D
    expression: [x >= T, x <= T]
    target: [1]
    weight: -1
"""
    with pytest.raises(ValueError, match="Number of expressions"):
        scheduler.schedule(yaml_content)


def test_shift_count_rejects_negative_and_non_numeric_target():
    negative_target_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: D
    expression: x >= T
    target: -1
    weight: -1
"""
    with pytest.raises(ValueError, match="Target must be non-negative"):
        scheduler.schedule(negative_target_yaml)

    non_numeric_target_yaml = negative_target_yaml.replace(b"target: -1", b"target: AVG_SHIFTS_PER_PERSON")
    with pytest.raises(ValueError, match="validation error"):
        scheduler.schedule(non_numeric_target_yaml)


def test_shift_count_rejects_invalid_weights_and_expression_for_squared_error():
    positive_weight_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: D
    expression: "|x - T|^2"
    target: 1
    weight: 1
"""
    with pytest.raises(ValueError, match="Weight must be non-positive"):
        scheduler.schedule(positive_weight_yaml)

    inf_weight_yaml = positive_weight_yaml.replace(b"weight: 1", b"weight: .inf")
    with pytest.raises(ValueError, match="'\\.inf' weights are not allowed"):
        scheduler.schedule(inf_weight_yaml)

    unsupported_expr_yaml = positive_weight_yaml.replace(b'"|x - T|^2"', b"x != T").replace(b"weight: 1", b"weight: -1")
    with pytest.raises(ValueError, match="Unsupported expression"):
        scheduler.schedule(unsupported_expr_yaml)


def test_shift_count_rejects_empty_expression_list():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: D
    expression: []
    target: []
    weight: -1
"""
    with pytest.raises(ValueError, match="Expression must not be empty"):
        scheduler.schedule(yaml_content)


def test_shift_count_rejects_empty_count_shift_types():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: []
    expression: x = T
    target: 0
    weight: .inf
"""
    with pytest.raises(ValueError, match="Non-empty count shift types are required"):
        scheduler.schedule(yaml_content)


def test_shift_count_accepts_shift_type_coefficients():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: A
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
    date: 2025-01-01
  - type: shift type requirement
    shiftType: A
    requiredNumPeople: 1
    date: 2025-01-02
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: [D, A]
    countShiftTypeCoefficients:
      - [D, 2]
      - [A, 3]
    expression: x = T
    target: 5
    weight: .inf
"""
    scheduler.schedule(yaml_content)


def test_shift_count_accepts_coefficients_covered_by_selected_group():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: A
  groups:
    - id: Work
      members: [D, A]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
    date: 2025-01-01
  - type: shift type requirement
    shiftType: A
    requiredNumPeople: 1
    date: 2025-01-02
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: Work
    countShiftTypeCoefficients:
      - [D, 2]
      - [A, 3]
    expression: x = T
    target: 5
    weight: .inf
"""
    scheduler.schedule(yaml_content)


def test_shift_count_rejects_invalid_shift_type_coefficients():
    coefficient_not_selected_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: A
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: [D]
    countShiftTypeCoefficients:
      - [A, 2]
    expression: x = T
    target: 1
    weight: .inf
"""
    with pytest.raises(ValueError, match="must be covered by countShiftTypes"):
        scheduler.schedule(coefficient_not_selected_yaml)

    for invalid_coefficient in (0, -1):
        invalid_coefficient_yaml = coefficient_not_selected_yaml.replace(
            b"- [A, 2]", f"- [D, {invalid_coefficient}]".encode()
        )
        with pytest.raises(ValueError, match="must be at least 1"):
            scheduler.schedule(invalid_coefficient_yaml)

    duplicate_coefficient_yaml = coefficient_not_selected_yaml.replace(
        b"""countShiftTypes: [D]
    countShiftTypeCoefficients:
      - [A, 2]""",
        b"""countShiftTypes: [D, G]
    countShiftTypeCoefficients:
      - [D, 2]
      - [G, 3]""",
    ).replace(
        b"""shiftTypes:
  items:
    - id: D
    - id: A""",
        b"""shiftTypes:
  items:
    - id: D
    - id: A
  groups:
    - id: G
      members: [D, A]""",
    )
    with pytest.raises(ValueError, match="Duplicate shift count coefficient"):
        scheduler.schedule(duplicate_coefficient_yaml)


def test_shift_count_rejects_overlapping_explicit_coefficient_one():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: A
  groups:
    - id: G
      members: [D, A]
preferences:
  - type: at most one shift per day
  - type: shift count
    person: n1
    countDates: ALL
    countShiftTypes: [D, G]
    countShiftTypeCoefficients:
      - [D, 1]
      - [G, 2]
    expression: x = T
    target: 1
    weight: .inf
"""
    with pytest.raises(ValueError, match="Duplicate shift count coefficient"):
        scheduler.schedule(yaml_content)


def test_shift_type_successions_rejects_history_all_and_group_ids():
    history_all_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
people:
  items:
    - id: n1
      history: [ALL]
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift type successions
    person: n1
    pattern: [D]
    weight: 1
"""
    with pytest.raises(ValueError, match="History must not include 'ALL', but got 'ALL'"):
        scheduler.schedule(history_all_yaml)

    history_group_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
people:
  items:
    - id: n1
      history: [G]
shiftTypes:
  items:
    - id: D
    - id: E
  groups:
    - id: G
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
  - type: shift type successions
    person: n1
    pattern: [D]
    weight: 1
"""
    with pytest.raises(ValueError, match="History must not include group ID, but got 'G'"):
        scheduler.schedule(history_group_yaml)


def test_people_history_rejects_invalid_shift_types_without_successions():
    empty_history_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
      history: [""]
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
"""
    with pytest.raises(ValueError, match="Unknown shift type ID in history: ''"):
        scheduler.schedule(empty_history_yaml)

    history_all_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
      history: [ALL]
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
"""
    with pytest.raises(ValueError, match="History must not include 'ALL', but got 'ALL'"):
        scheduler.schedule(history_all_yaml)

    history_group_yaml = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
      history: [G]
shiftTypes:
  items:
    - id: D
  groups:
    - id: G
      members: [D]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
"""
    with pytest.raises(ValueError, match="History must not include group ID, but got 'G'"):
        scheduler.schedule(history_group_yaml)


def test_shift_type_requirements_rejects_empty_shift_types():
    dummy_ctx = SimpleNamespace(
        n_days=1,
        map_did_d={},
        dates=SimpleNamespace(range=None),
        map_sid_s={},
    )
    pref = SimpleNamespace(date=None, shiftType="D", qualifiedPeople=None, preferredNumPeople=None, requiredNumPeople=1)

    original_parse_sids = preference_types.utils.parse_sids
    try:
        preference_types.utils.parse_sids = lambda *_args, **_kwargs: []
        with pytest.raises(ValueError, match="Non-empty shift types are required"):
            preference_types.shift_type_requirements(dummy_ctx, pref, 0)
    finally:
        preference_types.utils.parse_sids = original_parse_sids


def test_shift_type_requirements_parse_all_scalar_and_list_forms():
    map_sid_s = {
        "D": [0],
        "E": [1],
        "N": [2],
        "ALL": [0, 1, 2],
    }

    assert preference_types._parse_shift_type_requirement_groups("ALL", map_sid_s) == [[0, 1, 2]]
    assert preference_types._parse_shift_type_requirement_groups(["ALL"], map_sid_s) == [[0, 1, 2]]
    assert preference_types._parse_shift_type_requirement_groups([["ALL"]], map_sid_s) == [[0, 1, 2]]


@pytest.mark.parametrize(
    ("shift_type", "expected"),
    [
        ("D", [[0]]),
        ("Weekend", [[0, 2]]),
        (["D", "E"], [[0], [1]]),
        (["Weekend", "E"], [[0, 2], [1]]),
        ([["D", "E"]], [[0, 1]]),
        ([["Weekend", "E"]], [[0, 1, 2]]),
        ([["Weekend", "D"]], [[0, 2]]),
    ],
)
def test_shift_type_requirements_parse_grouped_and_top_level_shift_types(shift_type, expected):
    map_sid_s = {
        "D": [0],
        "E": [1],
        "N": [2],
        "Weekend": [0, 2],
    }

    assert preference_types._parse_shift_type_requirement_groups(shift_type, map_sid_s) == expected


def test_shift_type_requirements_allows_duplicate_expanded_coverage(caplog):
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
  groups:
    - id: DayOrEvening
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: DayOrEvening
    date: 2025-01-01
    requiredNumPeople: 0
  - type: shift type requirement
    shiftType: D
    date: 2025-01-01
    requiredNumPeople: 1
"""
    caplog.set_level(logging.INFO)

    scheduler.schedule(yaml_content)

    assert "Duplicate shift type requirement coverage for date '2025-01-01' and shift type 'D'" in caplog.text
    assert "applying all matching requirements" in caplog.text


def test_shift_type_requirements_allows_duplicate_nested_coverage(caplog):
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
    - id: N
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[D, E]]
    requiredNumPeople: 1
  - type: shift type requirement
    shiftType: [[E, N]]
    requiredNumPeople: 1
"""
    caplog.set_level(logging.INFO)

    scheduler.schedule(yaml_content)

    assert "Duplicate shift type requirement coverage for date '2025-01-01' and shift type 'E'" in caplog.text
    assert "applying all matching requirements" in caplog.text


def test_shift_type_requirements_allows_duplicate_nested_coverage_in_same_preference(caplog):
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
    - id: N
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[D, E], [E, N]]
    requiredNumPeople: 1
"""
    caplog.set_level(logging.INFO)

    scheduler.schedule(yaml_content)

    assert "Duplicate shift type requirement coverage for date '2025-01-01' and shift type 'E'" in caplog.text
    assert "applying all matching requirements" in caplog.text


def test_shift_type_requirements_allows_duplicate_aggregate_and_scalar_coverage(caplog):
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[D, E]]
    requiredNumPeople: 1
  - type: shift type requirement
    shiftType: E
    requiredNumPeople: 0
"""
    caplog.set_level(logging.INFO)

    scheduler.schedule(yaml_content)

    assert "Duplicate shift type requirement coverage for date '2025-01-01' and shift type 'E'" in caplog.text
    assert "applying all matching requirements" in caplog.text


def test_shift_type_requirements_rejects_coefficient_for_unselected_shift_type():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    shiftTypeCoefficients:
      - [E, 2]
    requiredNumPeople: 1
"""
    with pytest.raises(
        ValueError,
        match="Shift type requirement coefficient for 'E' must be covered by shiftType",
    ):
        scheduler.schedule(yaml_content)


def test_shift_type_requirements_rejects_invalid_coefficient():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    shiftTypeCoefficients:
      - [D, 0]
    requiredNumPeople: 1
"""
    with pytest.raises(ValueError, match="Shift type requirement coefficient for 'D' must be at least 1"):
        scheduler.schedule(yaml_content)


def test_shift_type_requirements_rejects_duplicate_expanded_coefficients():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
  groups:
    - id: Work
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[Work, D]]
    shiftTypeCoefficients:
      - [Work, 2]
      - [D, 3]
    requiredNumPeople: 1
"""
    with pytest.raises(ValueError, match="Duplicate shift type requirement coefficient for 'D'"):
        scheduler.schedule(yaml_content)


def test_shift_type_requirements_rejects_overlapping_explicit_coefficient_one():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
    - id: E
  groups:
    - id: Work
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[Work, D]]
    shiftTypeCoefficients:
      - [D, 1]
      - [Work, 2]
    requiredNumPeople: 1
"""
    with pytest.raises(ValueError, match="Duplicate shift type requirement coefficient for 'Work'"):
        scheduler.schedule(yaml_content)


def test_shift_type_requirements_rejects_coefficients_for_multiple_requirement_groups():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
    - id: n2
shiftTypes:
  items:
    - id: D
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [D, E]
    shiftTypeCoefficients:
      - [D, 2]
    requiredNumPeople: 1
"""
    with pytest.raises(
        ValueError,
        match="Shift type requirement coefficients are only supported when shiftType normalizes to one requirement group",
    ):
        scheduler.schedule(yaml_content)


def test_shift_type_successions_and_affinity_reject_non_list_inputs():
    dummy_ctx = SimpleNamespace(map_pid_p={"n1": [0]}, map_did_d={}, dates=SimpleNamespace(range=None))

    pref_successions = ShiftTypeSuccessionsPreference.model_validate(
        {
            "type": "shift type successions",
            "person": "n1",
            "pattern": ["D"],
            "weight": 1,
        }
    )
    pref_successions.pattern = "D"
    with pytest.raises(ValueError, match="Pattern must be a list"):
        preference_types.shift_type_successions(dummy_ctx, pref_successions, 0)

    pref_affinity = ShiftAffinityPreference.model_validate(
        {
            "type": "shift affinity",
            "date": "2025-01-01",
            "people1": ["n1"],
            "people2": ["n1"],
            "shiftTypes": ["D"],
            "weight": 1,
        }
    )

    date_range = SimpleNamespace(
        startDate=datetime.date(2025, 1, 1),
        endDate=datetime.date(2025, 1, 1),
    )
    dummy_affinity_ctx = SimpleNamespace(
        map_pid_p={"n1": [0]},
        map_sid_s={"D": [0]},
        map_did_d={"2025-01-01": [0]},
        dates=SimpleNamespace(range=date_range),
    )

    pref_affinity.people1 = "n1"
    with pytest.raises(ValueError, match="People1 must be a list"):
        preference_types.shift_affinity(dummy_affinity_ctx, pref_affinity, 0)

    pref_affinity.people1 = ["n1"]
    pref_affinity.people2 = "n1"
    with pytest.raises(ValueError, match="People2 must be a list"):
        preference_types.shift_affinity(dummy_affinity_ctx, pref_affinity, 0)

    pref_affinity.people2 = ["n1"]
    pref_affinity.shiftTypes = "D"
    with pytest.raises(ValueError, match="Shift types must be a list"):
        preference_types.shift_affinity(dummy_affinity_ctx, pref_affinity, 0)
