"""Tests for scheduling-data anonymization helpers."""

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

from nurse_scheduling.anonymize_scheduling_data import anonymize_people_ids_in_yaml
from nurse_scheduling.loader import _load_yaml


def test_anonymize_people_ids_in_yaml_updates_people_references():
    content = b"""\
apiVersion: alpha
dates:
  groups:
    - id: special-dates
      members: [Alice]
people:
  items:
    - id: Alice
    - id: Bob
  groups:
    - id: P1
      members: [Alice, Bob]
preferences:
  - type: shift request
    person: Alice
  - type: shift type requirement
    qualifiedPeople: [P1]
  - type: shift affinity
    people1: [Alice]
    people2: [[Bob, P1]]
export:
  formatting:
    - type: row
      people: [ALL, Alice, P1]
  extraRows:
    - type: count
      countPeople: [Bob, P1]
"""

    anonymized = anonymize_people_ids_in_yaml(content)

    data = _load_yaml(anonymized)
    assert data["people"]["items"] == [{"id": "P2"}, {"id": "P3"}]
    assert data["people"]["groups"] == [{"id": "P1", "members": ["P2", "P3"]}]
    assert data["dates"]["groups"] == [{"id": "special-dates", "members": ["Alice"]}]
    assert data["preferences"][0]["person"] == "P2"
    assert data["preferences"][1]["qualifiedPeople"] == ["P1"]
    assert data["preferences"][2]["people1"] == ["P2"]
    assert data["preferences"][2]["people2"] == [["P3", "P1"]]
    assert data["export"]["formatting"][0]["people"] == ["ALL", "P2", "P1"]
    assert data["export"]["extraRows"][0]["countPeople"] == ["P3", "P1"]
    assert b"Bob" not in anonymized


def test_anonymize_people_ids_in_yaml_returns_original_unparseable_yaml():
    content = b"people: ["

    assert anonymize_people_ids_in_yaml(content) is content
