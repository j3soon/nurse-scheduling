"""Anonymized optimizer submissions and restored workbook results."""

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

from io import BytesIO

import pytest
from openpyxl import load_workbook

from nurse_scheduling.ai.optimizer_privacy import OptimizerResultError, prepare_optimizer_schedule, restore_people_ids

from .ai_test_helper import base_schedule_payload, optimizer_workbook_bytes, parse_schedule, schedule_yaml


def named_schedule() -> str:
    payload = base_schedule_payload()
    payload["description"] = "Alice's private schedule"
    payload["people"]["items"] = [
        {"id": "Alice", "description": "Alice's note", "history": []},
        {"id": "Bob", "description": "Bob's note", "history": []},
    ]
    payload["people"]["groups"] = [
        {"id": "P1", "description": "Keep this group ID", "members": ["Alice", "Bob"]},
        {"id": "STAFF", "description": "Group note", "members": ["Alice"]},
    ]
    payload["preferences"][1]["person"] = ["Alice"]
    payload["preferences"].extend(
        [
            {
                "type": "shift type requirement",
                "shiftType": ["D"],
                "requiredNumPeople": 1,
                "qualifiedPeople": ["Alice", "P1"],
                "date": ["FIRST"],
            },
            {
                "type": "shift affinity",
                "date": ["FIRST"],
                "people1": ["Alice"],
                "people2": ["Bob"],
                "shiftTypes": ["D"],
            },
        ]
    )
    payload["export"]["formatting"] = [{"type": "row", "people": ["Alice"], "description": "Private formatting note"}]
    payload["export"]["extraRows"] = [
        {"type": "count", "header": "Count", "countShiftTypes": ["D"], "countPeople": ["Bob"]}
    ]
    return schedule_yaml(payload)


def test_optimizer_submission_matches_frontend_basic_anonymization() -> None:
    prepared = prepare_optimizer_schedule(named_schedule(), 1_000_000)
    outbound = parse_schedule(prepared.submission_yaml)

    assert prepared.original_id_by_anonymized_id == {"P2": "Alice", "P3": "Bob"}
    assert [person["id"] for person in outbound["people"]["items"]] == ["P2", "P3"]
    assert outbound["people"]["groups"][0]["id"] == "P1"
    assert outbound["people"]["groups"][0]["members"] == ["P2", "P3"]
    assert outbound["preferences"][1]["person"] == ["P2"]
    assert outbound["preferences"][2]["qualifiedPeople"] == ["P2", "P1"]
    assert outbound["preferences"][3]["people1"] == ["P2"]
    assert outbound["preferences"][3]["people2"] == ["P3"]
    assert outbound["export"]["formatting"][0]["people"] == ["P2"]
    assert outbound["export"]["extraRows"][0]["countPeople"] == ["P3"]
    assert "description" not in prepared.submission_yaml
    assert "Alice" not in prepared.submission_yaml
    assert "Bob" not in prepared.submission_yaml


def test_optimizer_workbook_restores_ids_before_download_and_attachment() -> None:
    prepared = prepare_optimizer_schedule(named_schedule(), 1_000_000)
    restored = restore_people_ids(
        optimizer_workbook_bytes(("P2", "P3")),
        prepared.original_id_by_anonymized_id,
        prepared.people_count,
    )

    workbook = load_workbook(BytesIO(restored), read_only=True)
    try:
        assert workbook.active["A3"].value == "Alice"
        assert workbook.active["A4"].value == "Bob"
    finally:
        workbook.close()


def test_optimizer_workbook_rejects_invalid_result() -> None:
    with pytest.raises(OptimizerResultError, match="not an XLSX"):
        restore_people_ids(b"not a workbook", {"P1": "Alice"}, 1)
