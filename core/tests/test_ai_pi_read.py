"""Tests for the Python port of Pi's text-file read behavior."""

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
import math

import pytest

from nurse_scheduling.ai.pi.read import (
    READ_TOOL_DESCRIPTION,
    ReadArgumentError,
    ReadInput,
    parse_read_input,
    read_parameters,
    render_read_result,
    truncate_head,
)


def test_pi_read_schema_and_defaults_match_the_pinned_source():
    assert "2000 lines or 50KB" in READ_TOOL_DESCRIPTION
    assert read_parameters() == {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read (relative or absolute)"},
            "offset": {"type": "number", "description": "Line number to start reading from (1-indexed)"},
            "limit": {"type": "number", "description": "Maximum number of lines to read"},
        },
        "required": ["path"],
    }


def test_pi_read_input_accepts_optional_ranges_and_ignores_extra_properties():
    parsed = parse_read_input('{"path":"schedule.yaml","offset":2,"limit":3,"future":true}')

    assert parsed == ReadInput("schedule.yaml", 2, 3)
    assert parse_read_input('{"path":""}').path == ""


@pytest.mark.parametrize("value", [math.inf, math.nan, True, "2"])
def test_pi_read_input_rejects_invalid_numbers(value):
    with pytest.raises(ReadArgumentError, match="Invalid offset"):
        parse_read_input(json.dumps({"path": "schedule.yaml", "offset": value}))


def test_pi_read_applies_one_indexed_offset_and_user_limit():
    result = render_read_result(b"one\ntwo\nthree\nfour", ReadInput("schedule.yaml", offset=2, limit=2))

    assert result.text == "two\nthree\n\n[1 more lines in file. Use offset=4 to continue.]"
    assert result.truncation is None


def test_pi_read_head_truncation_keeps_complete_first_lines():
    result = truncate_head("one\ntwo\nthree\n", max_lines=2, max_bytes=100)

    assert result.content == "one\ntwo"
    assert result.truncated
    assert result.truncated_by == "lines"
    assert result.total_lines == 3
    assert result.output_lines == 2


def test_pi_read_truncation_notice_points_to_the_next_offset():
    content = "\n".join(str(line) for line in range(2_001)).encode()

    result = render_read_result(content, ReadInput("large.txt"))

    assert result.text.startswith("0\n1\n")
    assert result.text.endswith("[Showing lines 1-2000 of 2001. Use offset=2001 to continue.]")
    assert result.truncation is not None


def test_pi_read_large_first_line_recommends_bounded_bash_fallback():
    result = render_read_result(b"x" * (50 * 1_024 + 1), ReadInput("wide.txt"))

    assert result.text.startswith("[Line 1 is 50.0KB, exceeds 50.0KB limit.")
    assert "sed -n '1p' wide.txt | head -c 51200" in result.text
    assert result.truncation is not None
    assert result.truncation.first_line_exceeds_limit


def test_pi_read_rejects_an_offset_beyond_the_file():
    with pytest.raises(ReadArgumentError, match=r"Offset 3 is beyond end of file \(2 lines total\)"):
        render_read_result(b"one\ntwo", ReadInput("small.txt", offset=3))
