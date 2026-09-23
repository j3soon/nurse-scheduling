"""Tests for web frontend schedule validation in the AI service."""

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

from nurse_scheduling.ai.validation import (
    MAX_ISSUE_MESSAGE_CHARS,
    MAX_VALIDATION_ISSUES,
    validate_frontend_schedule_yaml,
)

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml


def test_accepts_frontend_generated_schedule():
    result = validate_frontend_schedule_yaml(schedule_yaml(base_schedule_payload()), SCHEDULE_BYTE_LIMIT)

    assert result.valid
    assert result.issues == ()
    assert result.render() == "The schedule is valid for the web frontend editor."


def test_rejects_backend_only_shape_the_editor_cannot_represent():
    payload = base_schedule_payload()
    payload["preferences"].append(
        {
            "type": "shift type requirement",
            "shiftType": [["D", "N"]],
            "qualifiedPeople": ["P1"],
            "date": ["FIRST"],
            "requiredNumPeople": 1,
        }
    )

    result = validate_frontend_schedule_yaml(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert any("must not contain nested references" in issue.message for issue in result.issues)


def test_rejects_optional_canonical_field_required_by_the_editor():
    payload = base_schedule_payload()
    del payload["people"]["items"][1]["description"]

    result = validate_frontend_schedule_yaml(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert any("people.items[1].description is required" in issue.message for issue in result.issues)


def test_reports_field_errors_with_schedule_paths():
    payload = base_schedule_payload()
    payload["people"]["items"][0]["history"] = "not-a-list"

    result = validate_frontend_schedule_yaml(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert any(issue.location.startswith("people.items[0].history") for issue in result.issues)


def test_rejects_yaml_aliases():
    schedule = "anchor: &shared {}\napiVersion: alpha\ncopy: *shared\n"

    result = validate_frontend_schedule_yaml(schedule, SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert result.issues[0].location == "(document)"
    assert "aliases are not allowed" in result.issues[0].message


def test_rejects_unreadable_yaml():
    result = validate_frontend_schedule_yaml("people: [unclosed\n", SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert result.issues[0].location == "(document)"
    assert "not readable YAML" in result.issues[0].message


def test_rejects_non_mapping_document():
    result = validate_frontend_schedule_yaml("- just-a-list\n", SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert "top-level mapping" in result.issues[0].message


def test_rejects_schedule_over_the_byte_limit():
    schedule = schedule_yaml(base_schedule_payload())

    result = validate_frontend_schedule_yaml(schedule, len(schedule.encode("utf-8")) - 1)

    assert not result.valid
    assert "exceeds the limit" in result.issues[0].message


def test_bounds_the_reported_issue_count():
    payload = base_schedule_payload()
    payload["people"]["items"] = [{"id": [], "description": ""} for _ in range(MAX_VALIDATION_ISSUES)]

    result = validate_frontend_schedule_yaml(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert not result.valid
    assert len(result.issues) == MAX_VALIDATION_ISSUES
    assert result.omitted_issues > 0
    assert all(len(issue.message) <= MAX_ISSUE_MESSAGE_CHARS for issue in result.issues)
    assert f"{result.omitted_issues} further problems were not listed." in result.render()
