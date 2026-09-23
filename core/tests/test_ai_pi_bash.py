"""Tests for the Python port of Pi's Bash contract and output behavior."""

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

from nurse_scheduling.ai.pi.bash import (
    BASH_TOOL_DESCRIPTION,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    MAX_TIMEOUT_SECONDS,
    UPSTREAM_COMMIT,
    BashArgumentError,
    bash_parameters,
    format_size,
    parse_bash_input,
    prepare_bash_output,
    render_bash_result,
    truncate_tail,
)


def test_pi_bash_schema_and_defaults_match_the_pinned_source():
    assert UPSTREAM_COMMIT == "e266507b606b9552fa277252644054afd4384b11"
    assert DEFAULT_MAX_LINES == 2_000
    assert DEFAULT_MAX_BYTES == 50 * 1_024
    assert "last 2000 lines or 50KB" in BASH_TOOL_DESCRIPTION
    assert bash_parameters() == {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds (optional, no default timeout)",
            },
        },
        "required": ["command"],
    }


def test_pi_bash_input_accepts_optional_timeout_and_ignores_extra_properties():
    parsed = parse_bash_input('{"command":"rg people","timeout":2.5,"future":true}')

    assert parsed.command == "rg people"
    assert parsed.timeout == 2.5
    assert parse_bash_input('{"command":""}').command == ""


@pytest.mark.parametrize("timeout", [0, -1, math.inf, math.nan, True, "5", MAX_TIMEOUT_SECONDS + 1])
def test_pi_bash_input_rejects_invalid_timeouts(timeout):
    with pytest.raises(BashArgumentError, match="Invalid timeout"):
        parse_bash_input(f'{{"command":"sleep","timeout":{_json_value(timeout)}}}')


def test_pi_bash_tail_truncation_keeps_complete_last_lines():
    result = truncate_tail("one\ntwo\nthree\n", max_lines=2, max_bytes=100)

    assert result.content == "two\nthree"
    assert result.truncated
    assert result.truncated_by == "lines"
    assert result.total_lines == 3
    assert result.output_lines == 2


def test_pi_bash_tail_truncation_keeps_a_utf8_safe_partial_last_line():
    content = "first\n" + "€" * 10
    prepared = prepare_bash_output(content)
    result = truncate_tail(content, max_lines=2, max_bytes=7)

    assert result.content == "€€"
    assert result.output_bytes == 6
    assert result.last_line_partial
    assert prepared.last_line_bytes == 30


def test_pi_bash_result_matches_empty_nonzero_and_timeout_text():
    empty = prepare_bash_output("")

    success = render_bash_result(empty, full_output_path=None, exit_code=0, timed_out=False, timeout_seconds=10)
    failure = render_bash_result(empty, full_output_path=None, exit_code=7, timed_out=False, timeout_seconds=10)
    timeout = render_bash_result(empty, full_output_path=None, exit_code=124, timed_out=True, timeout_seconds=2.5)

    assert success.text == "(no output)"
    assert success.ok
    assert failure.text == "(no output)\n\nCommand exited with code 7"
    assert not failure.ok
    assert timeout.text == "Command timed out after 2.5 seconds"
    assert not timeout.ok


def test_pi_bash_truncation_notice_points_to_the_full_output():
    prepared = prepare_bash_output("\n".join(str(line) for line in range(2_001)))

    text = prepared.render("/tmp/pi-bash-test.log")

    assert text.startswith("1\n2\n")
    assert text.endswith("[Showing lines 2-2001 of 2001. Full output: /tmp/pi-bash-test.log]")
    assert format_size(50 * 1_024) == "50.0KB"


def _json_value(value) -> str:
    return json.dumps(value)
