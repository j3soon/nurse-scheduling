"""Python port of Pi's model-facing text-file read behavior."""

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

# Adapted from Pi's packages/coding-agent/src/core/tools/read.ts and truncate.ts
# at e266507b606b9552fa277252644054afd4384b11. Pi's MIT license is in LICENSE.
# This code is mostly AI generated.

import json
import math
from dataclasses import dataclass
from typing import Any

from .bash import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, UPSTREAM_COMMIT, format_size

READ_TOOL = "read"
READ_PROMPT_SNIPPET = "Read file contents"
READ_PROMPT_GUIDELINE = "Use read to examine files instead of cat or sed."
UPSTREAM_SOURCE = (
    f"https://github.com/earendil-works/pi/blob/{UPSTREAM_COMMIT}/packages/coding-agent/src/core/tools/read.ts"
)
READ_TOOL_DESCRIPTION = (
    "Read the contents of a text file. Output is truncated to "
    f"{DEFAULT_MAX_LINES} lines or {DEFAULT_MAX_BYTES // 1_024}KB (whichever is hit first). "
    "Use offset/limit for large files. When you need the full file, continue with offset until complete."
)


class ReadArgumentError(ValueError):
    """The model supplied arguments outside Pi's read schema."""


@dataclass(frozen=True)
class ReadInput:
    """Validated input for one Pi-compatible read call."""

    path: str
    offset: int | None = None
    limit: int | None = None


@dataclass(frozen=True)
class HeadTruncationResult:
    """Metadata produced by Pi's head-oriented output limit."""

    content: str
    truncated: bool
    truncated_by: str | None
    total_lines: int
    total_bytes: int
    output_lines: int
    output_bytes: int
    first_line_exceeds_limit: bool
    max_lines: int
    max_bytes: int


@dataclass(frozen=True)
class ReadResult:
    """Pi-compatible model text and truncation metadata for a text file."""

    text: str
    truncation: HeadTruncationResult | None = None


def read_parameters() -> dict[str, Any]:
    """Return Pi's read input schema in provider-neutral JSON Schema form."""
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read (relative or absolute)"},
            "offset": {"type": "number", "description": "Line number to start reading from (1-indexed)"},
            "limit": {"type": "number", "description": "Maximum number of lines to read"},
        },
        "required": ["path"],
    }


def parse_read_input(arguments: str) -> ReadInput:
    """Perform the validation Pi receives from its TypeBox tool schema."""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ReadArgumentError(f"Tool arguments are not valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("path"), str):
        raise ReadArgumentError("Tool arguments require a `path` string.")

    offset = _parse_optional_number(parsed, "offset")
    limit = _parse_optional_number(parsed, "limit")
    return ReadInput(parsed["path"], offset, limit)


def render_read_result(content: bytes, call: ReadInput) -> ReadResult:
    """Render one text file using Pi's offset, limit, and head truncation behavior."""
    text_content = content.decode("utf-8", errors="replace")
    all_lines = text_content.split("\n")
    total_file_lines = len(all_lines)
    start_line = max(0, (call.offset or 1) - 1)
    start_line_display = start_line + 1
    if start_line >= total_file_lines:
        raise ReadArgumentError(
            f"Offset {call.offset} is beyond end of file ({total_file_lines} lines total)"
        )

    user_limited_lines: int | None = None
    if call.limit is not None:
        end_line = min(start_line + call.limit, total_file_lines)
        selected_content = "\n".join(all_lines[start_line:end_line])
        user_limited_lines = max(0, end_line - start_line)
    else:
        selected_content = "\n".join(all_lines[start_line:])

    truncation = truncate_head(selected_content)
    if truncation.first_line_exceeds_limit:
        first_line_size = format_size(len(all_lines[start_line].encode("utf-8")))
        output = (
            f"[Line {start_line_display} is {first_line_size}, exceeds {format_size(DEFAULT_MAX_BYTES)} limit. "
            f"Use bash: sed -n '{start_line_display}p' {call.path} | head -c {DEFAULT_MAX_BYTES}]"
        )
        return ReadResult(output, truncation)

    if truncation.truncated:
        end_line_display = start_line_display + truncation.output_lines - 1
        next_offset = end_line_display + 1
        output = truncation.content
        if truncation.truncated_by == "lines":
            notice = (
                f"Showing lines {start_line_display}-{end_line_display} of {total_file_lines}. "
                f"Use offset={next_offset} to continue."
            )
        else:
            notice = (
                f"Showing lines {start_line_display}-{end_line_display} of {total_file_lines} "
                f"({format_size(DEFAULT_MAX_BYTES)} limit). Use offset={next_offset} to continue."
            )
        return ReadResult(f"{output}\n\n[{notice}]", truncation)

    if user_limited_lines is not None and start_line + user_limited_lines < total_file_lines:
        remaining = total_file_lines - (start_line + user_limited_lines)
        next_offset = start_line + user_limited_lines + 1
        return ReadResult(
            f"{truncation.content}\n\n[{remaining} more lines in file. Use offset={next_offset} to continue.]"
        )
    return ReadResult(truncation.content)


def truncate_head(
    content: str,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> HeadTruncationResult:
    """Keep the first complete lines that fit, as Pi does for read output."""
    total_bytes = len(content.encode("utf-8"))
    lines = _split_lines_for_counting(content)
    total_lines = len(lines)
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return HeadTruncationResult(
            content,
            False,
            None,
            total_lines,
            total_bytes,
            total_lines,
            total_bytes,
            False,
            max_lines,
            max_bytes,
        )

    first_line_bytes = len(lines[0].encode("utf-8"))
    if first_line_bytes > max_bytes:
        return HeadTruncationResult(
            "",
            True,
            "bytes",
            total_lines,
            total_bytes,
            0,
            0,
            True,
            max_lines,
            max_bytes,
        )

    output_lines: list[str] = []
    output_bytes = 0
    truncated_by = "lines"
    for line in lines[:max_lines]:
        line_bytes = len(line.encode("utf-8")) + (1 if output_lines else 0)
        if output_bytes + line_bytes > max_bytes:
            truncated_by = "bytes"
            break
        output_lines.append(line)
        output_bytes += line_bytes

    output_content = "\n".join(output_lines)
    return HeadTruncationResult(
        output_content,
        True,
        truncated_by,
        total_lines,
        total_bytes,
        len(output_lines),
        len(output_content.encode("utf-8")),
        False,
        max_lines,
        max_bytes,
    )


def _parse_optional_number(parsed: dict[str, Any], name: str) -> int | None:
    value = parsed.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ReadArgumentError(f"Invalid {name}: must be a finite number")
    return int(value)


def _split_lines_for_counting(content: str) -> list[str]:
    if not content:
        return []
    lines = content.split("\n")
    if content.endswith("\n"):
        lines.pop()
    return lines
