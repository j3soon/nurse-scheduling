"""Tests for model-readable frontend schedule schema guidance."""

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

from nurse_scheduling.ai.schema import MAX_SCHEMA_RESULT_CHARS, SCHEMA_PATHS, SCHEMA_TOPICS, render_schedule_schema
from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml
from nurse_scheduling.loader import _load_yaml

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml

EXAMPLE_PATHS = tuple(path for path, topic in SCHEMA_TOPICS.items() if topic.example is not None)


def test_schema_paths_are_unique_and_every_result_is_bounded():
    assert len(SCHEMA_PATHS) == len(set(SCHEMA_PATHS))
    assert set(SCHEMA_PATHS) == set(SCHEMA_TOPICS)
    assert EXAMPLE_PATHS

    results = [render_schedule_schema(), *(render_schedule_schema(path) for path in SCHEMA_PATHS)]

    assert all(result is not None for result in results)
    assert all(len(result) <= MAX_SCHEMA_RESULT_CHARS for result in results if result is not None)


def test_schema_separates_the_two_counting_preferences():
    """Staffing per shift and shifts per person read alike until the schema says otherwise."""
    index = render_schedule_schema("preferences")
    requirement = render_schedule_schema("preferences.shift type requirement")
    count = render_schedule_schema("preferences.shift count")

    assert index is not None
    assert "counts how many people a shift type needs on a date" in index
    assert "counts how many shifts one person works across dates" in index
    assert requirement is not None
    assert "number of people a shift type needs on a date" in requirement
    assert "Do not express this as a `shift count` preference" in requirement
    assert "Add `preferredNumPeople` with a finite `weight`" in requirement
    assert count is not None
    assert "not the people needed on a shift" in count
    assert "use `shift type requirement` instead" in count


def test_schema_guidance_preserves_selectors_and_defines_coefficient_pairs():
    root = render_schedule_schema()
    shift_count = render_schedule_schema("preferences.shift count")

    assert root is not None
    assert "Keep reserved selectors such as `ALL` literal" in root
    assert "shift type `D` is not group `Day`" in root
    assert "Quote a YAML string containing `: `" in root
    assert shift_count is not None
    assert "[[D, 1], [N, 2]]" in shift_count
    assert "not a mapping or a list of strings" in shift_count
    successions = render_schedule_schema("preferences.shift type successions")
    extra_rows = render_schedule_schema("export.extraRows")
    assert successions is not None
    assert "E followed by D is [E, D], not [Evening, Day]" in successions
    assert extra_rows is not None
    assert "Use ALL to count every person" in extra_rows
    assert "countPeople: [ALL]" in extra_rows
    date_range = render_schedule_schema("dates.range")
    people_items = render_schedule_schema("people.items")
    assert date_range is not None
    assert "same coordinated file edit" in date_range
    assert people_items is not None
    assert "every group membership" in people_items


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=EXAMPLE_PATHS)
def test_every_returned_yaml_example_is_frontend_compatible(path: str):
    topic = SCHEMA_TOPICS[path]
    assert topic.example is not None
    fragment = _load_yaml(topic.example.encode("utf-8"))
    payload = deepcopy(base_schedule_payload())

    if "preferences" in fragment:
        preferences = fragment["preferences"]
        if path == "preferences.at most one shift per day":
            payload["preferences"] = preferences
        else:
            payload["preferences"] = [{"type": "at most one shift per day"}, *preferences]
    else:
        section = next(iter(fragment))
        payload[section].update(fragment[section])

    result = validate_frontend_schedule_yaml(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert result.valid, result.render()
