"""Tests for the Python port of Pi's exact-text edit behavior."""

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

import pytest

from nurse_scheduling.ai.pi.edit import (
    EDIT_TOOL_DESCRIPTION,
    EditApplyError,
    EditArgumentError,
    EditInput,
    EditReplacement,
    apply_edit,
    edit_parameters,
    normalize_for_fuzzy_match,
    parse_edit_input,
    render_edit_result,
)


def test_pi_edit_schema_matches_the_pinned_source():
    schema = edit_parameters()

    assert "unique, non-overlapping" in EDIT_TOOL_DESCRIPTION
    assert schema["required"] == ["path", "edits"]
    assert schema["properties"]["path"] == {
        "type": "string",
        "description": "Path to the file to edit (relative or absolute)",
    }
    edits = schema["properties"]["edits"]
    assert edits["type"] == "array"
    assert edits["items"]["required"] == ["oldText", "newText"]


def test_pi_edit_input_accepts_multiple_replacements():
    parsed = parse_edit_input(
        json.dumps(
            {
                "path": "schedule.yaml",
                "edits": [
                    {"oldText": "one", "newText": "ONE"},
                    {"oldText": "two", "newText": "TWO"},
                ],
            }
        )
    )

    assert parsed == EditInput(
        "schedule.yaml",
        (EditReplacement("one", "ONE"), EditReplacement("two", "TWO")),
    )


@pytest.mark.parametrize(
    "edits",
    [
        {"oldText": "one", "newText": "ONE"},
        '[{"oldText":"one","newText":"ONE"}]',
        '{"oldText":"one","newText":"ONE"}',
    ],
)
def test_pi_edit_normalizes_single_and_stringified_edit_shapes(edits):
    parsed = parse_edit_input(json.dumps({"path": "file.txt", "edits": edits}))

    assert parsed.edits == (EditReplacement("one", "ONE"),)


def test_pi_edit_accepts_the_legacy_top_level_replacement_shape():
    parsed = parse_edit_input('{"path":"file.txt","oldText":"one","newText":"ONE"}')

    assert parsed.edits == (EditReplacement("one", "ONE"),)


@pytest.mark.parametrize(
    "arguments",
    [
        "{",
        "{}",
        '{"path":"file.txt","edits":[]}',
        '{"path":"file.txt","edits":[{"oldText":"one"}]}',
    ],
)
def test_pi_edit_rejects_invalid_arguments(arguments):
    with pytest.raises(EditArgumentError):
        parse_edit_input(arguments)


def test_pi_edit_matches_every_replacement_against_the_original_file():
    call = EditInput(
        "file.txt",
        (EditReplacement("one", "two"), EditReplacement("two", "three")),
    )

    edited = apply_edit(b"one two", call)

    assert edited == "two three"
    assert render_edit_result(call.path, len(call.edits)) == "Successfully replaced 2 block(s) in file.txt."


def test_pi_edit_preserves_bom_and_crlf_line_endings():
    call = EditInput("file.txt", (EditReplacement("one\ntwo", "ONE\nTWO"),))

    edited = apply_edit("\ufeffone\r\ntwo\r\nthree\r\n".encode(), call)

    assert edited == "\ufeffONE\r\nTWO\r\nthree\r\n"


def test_pi_edit_fuzzy_match_preserves_unchanged_lines_from_the_original():
    call = EditInput("file.txt", (EditReplacement("alpha\n", "changed\n"),))

    edited = apply_edit("alpha   \nkeep   \nquote “yes”\n".encode(), call)

    assert edited == "changed\nkeep   \nquote “yes”\n"
    assert normalize_for_fuzzy_match("quote “yes” — ok\u00a0") == 'quote "yes" - ok'


def test_pi_edit_rejects_missing_duplicate_empty_overlapping_and_unchanged_text():
    with pytest.raises(EditApplyError, match="Could not find the exact text"):
        apply_edit(b"one", EditInput("file.txt", (EditReplacement("missing", "new"),)))
    with pytest.raises(EditApplyError, match="Found 2 occurrences"):
        apply_edit(b"one one", EditInput("file.txt", (EditReplacement("one", "new"),)))
    with pytest.raises(EditApplyError, match="oldText must not be empty"):
        apply_edit(b"one", EditInput("file.txt", (EditReplacement("", "new"),)))
    with pytest.raises(EditApplyError, match=r"edits\[0\].*edits\[1\].*overlap"):
        apply_edit(
            b"one two three",
            EditInput(
                "file.txt",
                (EditReplacement("one two", "x"), EditReplacement("two three", "y")),
            ),
        )
    with pytest.raises(EditApplyError, match="replacement produced identical content"):
        apply_edit(b"one", EditInput("file.txt", (EditReplacement("one", "one"),)))
