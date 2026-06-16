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

from nurse_scheduling.anonymize_scheduling_data import anonymize_scheduling_data_in_yaml
from nurse_scheduling.loader import _load_yaml


def test_anonymize_scheduling_data_in_yaml_updates_people_references_and_removes_descriptions():
    content = b"""\
apiVersion: alpha
description: Sensitive schedule
dates:
  groups:
    - id: special-dates
      members: [Alice]
      description: Sensitive date group
people:
  items:
    - id: Alice
      description: Sensitive Alice
    - id: Bob
      description: Sensitive Bob
  groups:
    - id: P1
      members: [Alice, Bob]
      description: Sensitive people group
preferences:
  - type: shift request
    description: Sensitive request
    person: Alice
  - type: shift type requirement
    qualifiedPeople: [P1]
  - type: shift affinity
    people1: [Alice]
    people2: [[Bob, P1]]
export:
  formatting:
    - type: row
      description: Sensitive formatting
      people: [ALL, Alice, P1]
  extraRows:
    - type: count
      description: Sensitive count
      countPeople: [Bob, P1]
"""

    anonymized = anonymize_scheduling_data_in_yaml(content)

    data = _load_yaml(anonymized)
    assert "description" not in data
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
    assert b"Sensitive" not in anonymized


def test_anonymize_scheduling_data_in_yaml_returns_original_unparseable_yaml():
    content = b"people: ["

    assert anonymize_scheduling_data_in_yaml(content) is content


def test_anonymize_scheduling_data_in_yaml_removes_descriptions_with_malformed_people():
    content = b"""\
apiVersion: alpha
description: Sensitive schedule
people:
  items: Alice
preferences:
  - type: shift request
    description: Sensitive request
    person: Alice
"""

    anonymized = anonymize_scheduling_data_in_yaml(content)

    data = _load_yaml(anonymized)
    assert "description" not in data
    assert data["people"] == {"items": "Alice"}
    assert data["preferences"] == [{"type": "shift request", "person": "Alice"}]
    assert b"Sensitive" not in anonymized


def test_anonymize_scheduling_data_in_yaml_removes_descriptions():
    content = b"""\
apiVersion: alpha
description: Sensitive schedule
dates:
  items:
    - id: "01"
      description: Sensitive date
people:
  items:
    - id: Alice
      description: Sensitive person
  groups:
    - id: Team
      members: [Alice]
      description: Sensitive team
preferences:
  - type: shift request
    description: Sensitive request
    person: Alice
export:
  formatting:
    - type: row
      description: Sensitive formatting
      people: [Alice]
"""

    anonymized = anonymize_scheduling_data_in_yaml(content)

    data = _load_yaml(anonymized)
    assert "description" not in data
    assert data["dates"]["items"] == [{"id": "01"}]
    assert data["people"]["items"] == [{"id": "P1"}]
    assert data["people"]["groups"] == [{"id": "Team", "members": ["P1"]}]
    assert data["preferences"] == [{"type": "shift request", "person": "P1"}]
    assert data["export"]["formatting"] == [{"type": "row", "people": ["P1"]}]
    assert b"Sensitive" not in anonymized
