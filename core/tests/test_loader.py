"""Unit tests for YAML loading helpers."""

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

import pytest
from pydantic import ValidationError

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.loader import _load_yaml, load_data


SENTRY_MOJIBAKE_YAML = """\
嚜瘸piVersion: alpha
description: ''
dates:
  range:
    startDate: '2026-05-14'
    endDate: '2026-06-12'
  groups:
    - id: WORKDAY
      description: Taiwan workdays
      members: [05-14, 05-15, 05-18]
  items: []
people:
  items:
    - id: Person 1
      description: ''
      history: []
    - id: Person 2
      description: ''
      history: []
shiftTypes:
  items:
    - id: D
      description: Day
  groups: []
preferences:
  - type: at most one shift per day
export:
  formatting: []
  extraColumns: []
  extraRows: []
"""


VALID_YAML_BODY = """\
{api_version_key}: alpha
dates:
  range:
    startDate: 2026-05-14
    endDate: 2026-05-14
people:
  items:
    - id: Person 1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
"""


def test_load_data_accepts_utf8_bom_api_version_key():
    data = load_data(VALID_YAML_BODY.format(api_version_key="apiVersion").encode("utf-8-sig"))

    assert data.apiVersion == "alpha"


def test_load_data_rejects_sentry_mojibake_api_version_key():
    with pytest.raises(ValidationError, match="apiVersion"):
        load_data(SENTRY_MOJIBAKE_YAML.encode("utf-8"))


@pytest.mark.parametrize(
    "api_version_key",
    [
        "ï»¿apiVersion",
        "嚜瘸piVersion",
        "锘縜piVersion",
    ],
)
def test_load_data_rejects_bom_corrupted_api_version_keys(api_version_key):
    content = VALID_YAML_BODY.format(api_version_key=api_version_key).encode("utf-8")

    with pytest.raises(ValidationError, match="apiVersion"):
        load_data(content)


@pytest.mark.parametrize(
    "api_version_key",
    [
        "ï»¿apiVersion",
        "嚜瘸piVersion",
        "锘縜piVersion",
    ],
)
def test_load_yaml_preserves_bom_corrupted_api_version_keys(api_version_key):
    data = _load_yaml(VALID_YAML_BODY.format(api_version_key=api_version_key).encode("utf-8"))

    assert data[api_version_key] == "alpha"
    assert "apiVersion" not in data
