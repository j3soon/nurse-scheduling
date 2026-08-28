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

import json

from nurse_scheduling.ai.validation import (
    MAX_ISSUE_MESSAGE_CHARS,
    MAX_VALIDATION_ISSUES,
    validate_frontend_schedule_yaml,
)

LARGE_LIMIT = 1_000_000


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


def _yaml(payload: dict) -> str:
    # JSON is valid YAML 1.2, so tests mutate a payload and serialize it directly.
    return json.dumps(payload)


def test_accepts_frontend_generated_schedule():
    result = validate_frontend_schedule_yaml(_yaml(_base_payload()), LARGE_LIMIT)

    assert result.valid
    assert result.issues == ()
    assert result.render() == "The schedule is valid for the web frontend editor."


def test_rejects_backend_only_shape_the_editor_cannot_represent():
    payload = _base_payload()
    payload["preferences"].append(
        {
            "type": "shift type requirement",
            "shiftType": [["D", "N"]],
            "qualifiedPeople": ["P1"],
            "date": ["FIRST"],
            "requiredNumPeople": 1,
        }
    )

    result = validate_frontend_schedule_yaml(_yaml(payload), LARGE_LIMIT)

    assert not result.valid
    assert any("must not contain nested references" in issue.message for issue in result.issues)


def test_rejects_optional_canonical_field_required_by_the_editor():
    payload = _base_payload()
    del payload["people"]["items"][1]["description"]

    result = validate_frontend_schedule_yaml(_yaml(payload), LARGE_LIMIT)

    assert not result.valid
    assert any("people.items[1].description is required" in issue.message for issue in result.issues)


def test_reports_field_errors_with_schedule_paths():
    payload = _base_payload()
    payload["people"]["items"][0]["history"] = "not-a-list"

    result = validate_frontend_schedule_yaml(_yaml(payload), LARGE_LIMIT)

    assert not result.valid
    assert any(issue.location.startswith("people.items[0].history") for issue in result.issues)


def test_rejects_yaml_aliases():
    schedule = "anchor: &shared {}\napiVersion: alpha\ncopy: *shared\n"

    result = validate_frontend_schedule_yaml(schedule, LARGE_LIMIT)

    assert not result.valid
    assert result.issues[0].location == "(document)"
    assert "aliases are not allowed" in result.issues[0].message


def test_rejects_unreadable_yaml():
    result = validate_frontend_schedule_yaml("people: [unclosed\n", LARGE_LIMIT)

    assert not result.valid
    assert result.issues[0].location == "(document)"
    assert "not readable YAML" in result.issues[0].message


def test_rejects_non_mapping_document():
    result = validate_frontend_schedule_yaml("- just-a-list\n", LARGE_LIMIT)

    assert not result.valid
    assert "top-level mapping" in result.issues[0].message


def test_rejects_schedule_over_the_byte_limit():
    schedule = _yaml(_base_payload())

    result = validate_frontend_schedule_yaml(schedule, len(schedule.encode("utf-8")) - 1)

    assert not result.valid
    assert "exceeds the limit" in result.issues[0].message


def test_bounds_the_reported_issue_count():
    payload = _base_payload()
    payload["people"]["items"] = [{"id": [], "description": ""} for _ in range(MAX_VALIDATION_ISSUES)]

    result = validate_frontend_schedule_yaml(_yaml(payload), LARGE_LIMIT)

    assert not result.valid
    assert len(result.issues) == MAX_VALIDATION_ISSUES
    assert result.omitted_issues > 0
    assert all(len(issue.message) <= MAX_ISSUE_MESSAGE_CHARS for issue in result.issues)
    assert f"{result.omitted_issues} further problems were not listed." in result.render()
