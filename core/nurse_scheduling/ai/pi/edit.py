"""Python port of Pi's model-facing exact-text edit behavior."""

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

# Adapted from Pi's packages/coding-agent/src/core/tools/edit.ts and edit-diff.ts
# at e266507b606b9552fa277252644054afd4384b11. Pi's MIT license is in LICENSE.
# This code is mostly AI generated.

import json
import unicodedata
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .bash import UPSTREAM_COMMIT

EDIT_TOOL = "edit"
EDIT_PROMPT_SNIPPET = "Make precise file edits with exact text replacement, including multiple disjoint edits in one call"
EDIT_PROMPT_GUIDELINES = (
    "Use edit for precise changes (edits[].oldText must match exactly)",
    (
        "When changing multiple separate locations in one file, use one edit call with multiple entries in edits[] "
        "instead of multiple edit calls"
    ),
    (
        "Each edits[].oldText is matched against the original file, not after earlier edits are applied. Do not emit "
        "overlapping or nested edits. Merge nearby changes into one edit."
    ),
    (
        "Keep edits[].oldText as small as possible while still being unique in the file. Do not pad with large "
        "unchanged regions."
    ),
)
UPSTREAM_SOURCE = (
    f"https://github.com/earendil-works/pi/blob/{UPSTREAM_COMMIT}/packages/coding-agent/src/core/tools/edit.ts"
)
EDIT_TOOL_DESCRIPTION = (
    "Edit a single file using exact text replacement. Every edits[].oldText must match a unique, non-overlapping "
    "region of the original file. If two changes affect the same block or nearby lines, merge them into one edit "
    "instead of emitting overlapping edits. Do not include large unchanged regions just to connect distant changes."
)


class EditArgumentError(ValueError):
    """The model supplied arguments outside Pi's edit schema."""


class EditApplyError(ValueError):
    """Pi's matching rules rejected a proposed replacement."""


@dataclass(frozen=True)
class EditReplacement:
    """One exact replacement supplied in a Pi edit call."""

    old_text: str
    new_text: str


@dataclass(frozen=True)
class EditInput:
    """Validated input for one Pi-compatible edit call."""

    path: str
    edits: tuple[EditReplacement, ...]


@dataclass(frozen=True)
class _Match:
    found: bool
    index: int
    match_length: int
    used_fuzzy_match: bool


@dataclass(frozen=True)
class _MatchedEdit:
    edit_index: int
    match_index: int
    match_length: int
    new_text: str


@dataclass(frozen=True)
class _LineSpan:
    start: int
    end: int


def edit_parameters() -> dict[str, Any]:
    """Return Pi's edit input schema in provider-neutral JSON Schema form."""
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit (relative or absolute)"},
            "edits": {
                "type": "array",
                "description": (
                    "One or more targeted replacements. Each edit is matched against the original file, not "
                    "incrementally. Do not include overlapping or nested edits. If two changes touch the same block "
                    "or nearby lines, merge them into one edit instead."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "oldText": {
                            "type": "string",
                            "description": (
                                "Exact text for one targeted replacement. It must be unique in the original file and "
                                "must not overlap with any other edits[].oldText in the same call."
                            ),
                        },
                        "newText": {"type": "string", "description": "Replacement text for this targeted edit."},
                    },
                    "required": ["oldText", "newText"],
                },
            },
        },
        "required": ["path", "edits"],
    }


def parse_edit_input(arguments: str) -> EditInput:
    """Normalize model compatibility shapes before validating Pi's edit schema."""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise EditArgumentError(f"Tool arguments are not valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("path"), str):
        raise EditArgumentError("Tool arguments require a `path` string.")

    raw_edits = parsed.get("edits")
    if isinstance(raw_edits, str):
        try:
            decoded_edits = json.loads(raw_edits)
        except json.JSONDecodeError:
            decoded_edits = raw_edits
        if isinstance(decoded_edits, list) or _is_edit_mapping(decoded_edits):
            raw_edits = decoded_edits
    if _is_edit_mapping(raw_edits):
        raw_edits = [raw_edits]

    legacy_old_text = parsed.get("oldText")
    legacy_new_text = parsed.get("newText")
    if isinstance(legacy_old_text, str) and isinstance(legacy_new_text, str):
        raw_edits = [*raw_edits, {"oldText": legacy_old_text, "newText": legacy_new_text}] if isinstance(
            raw_edits, list
        ) else [{"oldText": legacy_old_text, "newText": legacy_new_text}]

    if not isinstance(raw_edits, list) or not raw_edits:
        raise EditArgumentError("Edit tool input is invalid. edits must contain at least one replacement.")
    if not all(_is_edit_mapping(edit) for edit in raw_edits):
        raise EditArgumentError("Each edit requires `oldText` and `newText` strings.")
    edits = tuple(EditReplacement(edit["oldText"], edit["newText"]) for edit in raw_edits)
    return EditInput(parsed["path"], edits)


def apply_edit(content: bytes, call: EditInput) -> str:
    """Apply Pi's unique, non-overlapping replacements and preserve file encoding style."""
    raw_content = content.decode("utf-8", errors="replace")
    bom, text = _split_bom(raw_content)
    original_ending = detect_line_ending(text)
    normalized_content = normalize_to_lf(text)
    new_content = apply_edits_to_normalized_content(normalized_content, call.edits, call.path)
    return bom + restore_line_endings(new_content, original_ending)


def render_edit_result(path: str, replacement_count: int) -> str:
    """Render Pi's successful edit result."""
    return f"Successfully replaced {replacement_count} block(s) in {path}."


def detect_line_ending(content: str) -> str:
    """Detect whether the first newline uses CRLF, matching Pi."""
    crlf_index = content.find("\r\n")
    lf_index = content.find("\n")
    if lf_index == -1 or crlf_index == -1:
        return "\n"
    return "\r\n" if crlf_index < lf_index else "\n"


def normalize_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def restore_line_endings(text: str, ending: str) -> str:
    return text.replace("\n", "\r\n") if ending == "\r\n" else text


def normalize_for_fuzzy_match(text: str) -> str:
    """Apply the limited whitespace and Unicode normalization used by Pi."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return normalized.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201a": "'",
                "\u201b": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u201e": '"',
                "\u201f": '"',
                "\u2010": "-",
                "\u2011": "-",
                "\u2012": "-",
                "\u2013": "-",
                "\u2014": "-",
                "\u2015": "-",
                "\u2212": "-",
                "\u00a0": " ",
                "\u2002": " ",
                "\u2003": " ",
                "\u2004": " ",
                "\u2005": " ",
                "\u2006": " ",
                "\u2007": " ",
                "\u2008": " ",
                "\u2009": " ",
                "\u200a": " ",
                "\u202f": " ",
                "\u205f": " ",
                "\u3000": " ",
            }
        )
    )


def apply_edits_to_normalized_content(
    normalized_content: str,
    edits: tuple[EditReplacement, ...],
    path: str,
) -> str:
    """Match all edits against one original snapshot and apply them in reverse order."""
    normalized_edits = tuple(
        EditReplacement(normalize_to_lf(edit.old_text), normalize_to_lf(edit.new_text)) for edit in edits
    )
    for index, edit in enumerate(normalized_edits):
        if not edit.old_text:
            raise EditApplyError(_empty_old_text_error(path, index, len(normalized_edits)))

    initial_matches = tuple(_fuzzy_find_text(normalized_content, edit.old_text) for edit in normalized_edits)
    used_fuzzy_match = any(match.used_fuzzy_match for match in initial_matches)
    replacement_base = normalize_for_fuzzy_match(normalized_content) if used_fuzzy_match else normalized_content

    matched_edits: list[_MatchedEdit] = []
    for index, edit in enumerate(normalized_edits):
        match = _fuzzy_find_text(replacement_base, edit.old_text)
        if not match.found:
            raise EditApplyError(_not_found_error(path, index, len(normalized_edits)))
        occurrences = normalize_for_fuzzy_match(replacement_base).count(normalize_for_fuzzy_match(edit.old_text))
        if occurrences > 1:
            raise EditApplyError(_duplicate_error(path, index, len(normalized_edits), occurrences))
        matched_edits.append(_MatchedEdit(index, match.index, match.match_length, edit.new_text))

    matched_edits.sort(key=lambda edit: edit.match_index)
    for previous, current in pairwise(matched_edits):
        if previous.match_index + previous.match_length > current.match_index:
            raise EditApplyError(
                f"edits[{previous.edit_index}] and edits[{current.edit_index}] overlap in {path}. "
                "Merge them into one edit or target disjoint regions."
            )

    if used_fuzzy_match:
        new_content = _apply_replacements_preserving_unchanged_lines(
            normalized_content,
            replacement_base,
            matched_edits,
        )
    else:
        new_content = _apply_replacements(replacement_base, matched_edits)
    if normalized_content == new_content:
        raise EditApplyError(_no_change_error(path, len(normalized_edits)))
    return new_content


def _fuzzy_find_text(content: str, old_text: str) -> _Match:
    exact_index = content.find(old_text)
    if exact_index != -1:
        return _Match(True, exact_index, len(old_text), False)
    fuzzy_content = normalize_for_fuzzy_match(content)
    fuzzy_old_text = normalize_for_fuzzy_match(old_text)
    fuzzy_index = fuzzy_content.find(fuzzy_old_text)
    if fuzzy_index == -1:
        return _Match(False, -1, 0, False)
    return _Match(True, fuzzy_index, len(fuzzy_old_text), True)


def _apply_replacements(content: str, replacements: list[_MatchedEdit], offset: int = 0) -> str:
    result = content
    for replacement in reversed(replacements):
        match_index = replacement.match_index - offset
        result = (
            result[:match_index]
            + replacement.new_text
            + result[match_index + replacement.match_length :]
        )
    return result


def _apply_replacements_preserving_unchanged_lines(
    original_content: str,
    base_content: str,
    replacements: list[_MatchedEdit],
) -> str:
    original_lines = _split_lines_with_endings(original_content)
    base_lines = _line_spans(base_content)
    if len(original_lines) != len(base_lines):
        raise EditApplyError("Cannot preserve unchanged lines because the base content has a different line count.")

    groups: list[tuple[int, int, list[_MatchedEdit]]] = []
    for replacement in sorted(replacements, key=lambda edit: edit.match_index):
        start_line, end_line = _replacement_line_range(base_lines, replacement)
        if groups and start_line < groups[-1][1]:
            prior_start, prior_end, prior_replacements = groups[-1]
            groups[-1] = (prior_start, max(prior_end, end_line), [*prior_replacements, replacement])
        else:
            groups.append((start_line, end_line, [replacement]))

    original_line_index = 0
    result = ""
    for start_line, end_line, group_replacements in groups:
        result += "".join(original_lines[original_line_index:start_line])
        group_start_offset = base_lines[start_line].start
        group_end_offset = base_lines[end_line - 1].end
        result += _apply_replacements(
            base_content[group_start_offset:group_end_offset],
            group_replacements,
            group_start_offset,
        )
        original_line_index = end_line
    return result + "".join(original_lines[original_line_index:])


def _replacement_line_range(lines: list[_LineSpan], replacement: _MatchedEdit) -> tuple[int, int]:
    replacement_end = replacement.match_index + replacement.match_length
    start_line = next(
        (
            index
            for index, line in enumerate(lines)
            if replacement.match_index >= line.start and replacement.match_index < line.end
        ),
        -1,
    )
    if start_line == -1:
        raise EditApplyError("Replacement range is outside the base content.")
    end_line = start_line
    while end_line < len(lines) and lines[end_line].end < replacement_end:
        end_line += 1
    if end_line >= len(lines):
        raise EditApplyError("Replacement range is outside the base content.")
    return start_line, end_line + 1


def _line_spans(content: str) -> list[_LineSpan]:
    offset = 0
    spans: list[_LineSpan] = []
    for line in _split_lines_with_endings(content):
        spans.append(_LineSpan(offset, offset + len(line)))
        offset += len(line)
    return spans


def _split_lines_with_endings(content: str) -> list[str]:
    return content.splitlines(keepends=True)


def _split_bom(content: str) -> tuple[str, str]:
    return ("\ufeff", content[1:]) if content.startswith("\ufeff") else ("", content)


def _is_edit_mapping(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("oldText"), str)
        and isinstance(value.get("newText"), str)
    )


def _not_found_error(path: str, index: int, total: int) -> str:
    if total == 1:
        return (
            f"Could not find the exact text in {path}. "
            "The old text must match exactly including all whitespace and newlines."
        )
    return (
        f"Could not find edits[{index}] in {path}. "
        "The oldText must match exactly including all whitespace and newlines."
    )


def _duplicate_error(path: str, index: int, total: int, occurrences: int) -> str:
    if total == 1:
        return (
            f"Found {occurrences} occurrences of the text in {path}. The text must be unique. "
            "Please provide more context to make it unique."
        )
    return (
        f"Found {occurrences} occurrences of edits[{index}] in {path}. Each oldText must be unique. "
        "Please provide more context to make it unique."
    )


def _empty_old_text_error(path: str, index: int, total: int) -> str:
    return f"oldText must not be empty in {path}." if total == 1 else f"edits[{index}].oldText must not be empty in {path}."


def _no_change_error(path: str, total: int) -> str:
    if total == 1:
        return (
            f"No changes made to {path}. The replacement produced identical content. "
            "This might indicate an issue with special characters or the text not existing as expected."
        )
    return f"No changes made to {path}. The replacements produced identical content."
