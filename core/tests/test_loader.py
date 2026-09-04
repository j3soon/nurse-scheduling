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
import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from ruamel.yaml.error import YAMLError

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.loader import (
    MAX_EXPANDED_NODES,
    MAX_NESTING_DEPTH,
    SchedulingDataTooComplexError,
    _load_yaml,
    load_data,
    measure_yaml_expansion,
)

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


def _alias_bomb(depth: int = 8, width: int = 9) -> bytes:
    """Build a document whose aliases expand to width ** depth references."""
    content = b"apiVersion: alpha\ndescription: &a [" + b",".join([b"x"] * width) + b"]\n"
    for index in range(1, depth):
        previous = chr(ord("a") + index - 1)
        current = chr(ord("a") + index)
        row = ",".join(f"*{previous}" for _ in range(width))
        content += f"k{current}: &{current} [{row}]\n".encode()
    return content


def test_alias_expansion_is_refused_before_anything_walks_it():
    """A few hundred bytes expanded to hundreds of millions of references."""
    bomb = _alias_bomb()

    assert len(bomb) < 1024
    with pytest.raises(SchedulingDataTooComplexError):
        measure_yaml_expansion(bomb)
    with pytest.raises(SchedulingDataTooComplexError):
        load_data(bomb)


def test_modest_alias_use_is_still_accepted():
    """Aliases are legitimate in hand-written data, so only the expansion is bounded."""
    base = b"apiVersion: alpha\npeople: &people [Alice, Bob]\n"
    one_alias = base + b"a: *people\n"
    two_aliases = one_alias + b"b: *people\n"

    # Each alias counts the three nodes it stands for, plus its own key.
    assert measure_yaml_expansion(two_aliases).nodes - measure_yaml_expansion(one_alias).nodes == 4
    assert measure_yaml_expansion(two_aliases).nodes < MAX_EXPANDED_NODES
    assert measure_yaml_expansion(two_aliases).aliases == 2


def test_a_real_scenario_stays_far_below_the_limit():
    scenario = Path(__file__).parent / "testcases/real/large-ward-with-87-people-2025-11.yaml"

    measured = measure_yaml_expansion(scenario.read_bytes())

    assert measured.nodes < MAX_EXPANDED_NODES // 10
    # This project's own data never uses an alias.
    assert measured.aliases == 0


def test_the_limit_is_reported_with_the_number_it_exceeded():
    with pytest.raises(SchedulingDataTooComplexError, match="200000"):
        measure_yaml_expansion(_alias_bomb())


def test_deep_nesting_is_refused_before_it_is_read():
    """Parsing costs grow faster than depth, so a deep document must not be read through."""
    depth = 100_000
    payload = b"apiVersion: alpha\nx: " + b"[" * depth + b"]" * depth + b"\n"

    with pytest.raises(SchedulingDataTooComplexError, match=str(MAX_NESTING_DEPTH)):
        measure_yaml_expansion(payload)


def test_an_unsupported_version_directive_reads_as_a_yaml_error():
    """The parser raises a bare assertion here, which callers cannot separate from a bug."""
    with pytest.raises(YAMLError):
        measure_yaml_expansion(b"%YAML 1.3\n---\na: 1\n")
    with pytest.raises(YAMLError):
        load_data(b"%YAML 1.3\n---\na: 1\n")


def test_nesting_is_refused_before_the_scanner_reads_it():
    """The scanner works proportionally to its depth, so depth must be refused first."""
    payload = b"apiVersion: alpha\nx: " + b"[" * 2000 + b"]" * 2000

    started = time.monotonic()
    with pytest.raises(SchedulingDataTooComplexError):
        measure_yaml_expansion(payload)

    # Reading this through the scanner took a quarter second before it was refused early.
    assert time.monotonic() - started < 0.05
