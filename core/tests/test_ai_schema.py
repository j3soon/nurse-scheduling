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
