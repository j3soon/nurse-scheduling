"""Tests for the Python port of Pi's complete-file write behavior."""

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

import pytest

from nurse_scheduling.ai.pi.write import (
    WRITE_TOOL_DESCRIPTION,
    WriteArgumentError,
    WriteInput,
    parse_write_input,
    render_write_result,
    write_parameters,
)


def test_pi_write_schema_matches_the_pinned_source():
    assert "overwrites if it does" in WRITE_TOOL_DESCRIPTION
    assert write_parameters() == {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write (relative or absolute)"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["path", "content"],
    }


def test_pi_write_input_accepts_content_and_ignores_extra_properties():
    parsed = parse_write_input('{"path":"new.txt","content":"hello","future":true}')

    assert parsed == WriteInput("new.txt", "hello")
    assert render_write_result(parsed.path) == "Successfully wrote to new.txt"


@pytest.mark.parametrize(
    "arguments",
    ["{", "{}", '{"path":"new.txt"}', '{"path":1,"content":"x"}', '{"path":"new.txt","content":1}'],
)
def test_pi_write_rejects_invalid_arguments(arguments):
    with pytest.raises(WriteArgumentError):
        parse_write_input(arguments)
