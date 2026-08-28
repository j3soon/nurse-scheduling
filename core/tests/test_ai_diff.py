"""Tests for structural schedule diffs in the AI service."""

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

from nurse_scheduling.ai.diff import MAX_DIFF_ENTRIES, MAX_DIFF_VALUE_CHARS, diff_schedules

from .ai_test_helper import base_schedule_payload


def _locations(diff) -> list[str]:
    return [entry.location for entry in diff.entries]


def test_reports_no_changes_for_equal_schedules():
    diff = diff_schedules(base_schedule_payload(), base_schedule_payload())

    assert diff.entries == ()
    assert diff.render() == "No changes."


def test_reports_a_changed_value_with_its_path():
    after = base_schedule_payload()
    after["people"]["items"][0]["description"] = "Head nurse"

    diff = diff_schedules(base_schedule_payload(), after)

    assert _locations(diff) == ["people.items[0].description"]
    assert diff.render() == '- people.items[0].description: "" -> "Head nurse"'


def test_reports_added_and_removed_mapping_keys():
    after = base_schedule_payload()
    del after["description"]
    after["people"]["items"][0]["note"] = "added"

    diff = diff_schedules(base_schedule_payload(), after)

    kinds = {entry.location: entry.kind for entry in diff.entries}
    assert kinds["description"] == "removed"
    assert kinds["people.items[0].note"] == "added"


def test_insertion_reports_one_entry_instead_of_shifting_every_later_entry():
    after = base_schedule_payload()
    after["people"]["items"].insert(0, {"id": "P0", "description": "", "history": []})

    diff = diff_schedules(base_schedule_payload(), after)

    assert _locations(diff) == ["people.items[0]"]
    assert diff.entries[0].kind == "added"


def test_removal_is_visible_even_though_the_result_stays_valid():
    after = base_schedule_payload()
    del after["people"]["items"][1]
    after["people"]["groups"][0]["members"] = ["P1"]

    diff = diff_schedules(base_schedule_payload(), after)

    kinds = {entry.location: entry.kind for entry in diff.entries}
    assert kinds["people.items[1]"] == "removed"
    assert "P2" in diff.render()


def test_bounds_the_reported_changes():
    before = base_schedule_payload()
    before["people"]["items"] = [{"id": f"P{index}", "description": ""} for index in range(MAX_DIFF_ENTRIES + 10)]
    after = base_schedule_payload()
    after["people"]["items"] = [{"id": f"P{index}", "description": "renamed"} for index in range(MAX_DIFF_ENTRIES + 10)]

    diff = diff_schedules(before, after)

    assert len(diff.entries) == MAX_DIFF_ENTRIES
    assert diff.omitted == 10
    assert "10 further changes were not listed." in diff.render()


def test_bounds_one_rendered_value():
    after = base_schedule_payload()
    after["description"] = "x" * (MAX_DIFF_VALUE_CHARS * 2)

    diff = diff_schedules(base_schedule_payload(), after)

    assert len(diff.entries[0].after) == MAX_DIFF_VALUE_CHARS
    assert diff.entries[0].after.endswith("...")
