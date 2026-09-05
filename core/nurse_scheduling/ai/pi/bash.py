"""Python port of Pi's model-facing Bash contract and output behavior."""

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

# Adapted from Pi's packages/coding-agent/src/core/tools/bash.ts and truncate.ts
# at e266507b606b9552fa277252644054afd4384b11. Pi's MIT license is in LICENSE.
# This code is mostly AI generated.

import json
import math
from dataclasses import dataclass
from typing import Any

BASH_TOOL = "bash"
BASH_PROMPT_SNIPPET = "Execute bash commands (ls, grep, find, etc.)"
DEFAULT_MAX_LINES = 2_000
DEFAULT_MAX_BYTES = 50 * 1_024
MAX_TIMEOUT_SECONDS = 2_147_483_647 / 1_000
UPSTREAM_COMMIT = "e266507b606b9552fa277252644054afd4384b11"
UPSTREAM_SOURCE = (
    f"https://github.com/earendil-works/pi/blob/{UPSTREAM_COMMIT}/packages/coding-agent/src/core/tools/bash.ts"
)

BASH_TOOL_DESCRIPTION = (
    "Execute a bash command in the current working directory. Returns stdout and stderr. "
    f"Output is truncated to last {DEFAULT_MAX_LINES} lines or {DEFAULT_MAX_BYTES // 1_024}KB "
    "(whichever is hit first). If truncated, full output is saved to a temp file. "
    "Optionally provide a timeout in seconds."
)


class BashArgumentError(ValueError):
    """The model supplied arguments outside Pi's Bash schema."""


@dataclass(frozen=True)
class BashInput:
    """Validated input for one Pi-compatible Bash call."""

    command: str
    timeout: float | None = None


@dataclass(frozen=True)
class TruncationResult:
    """Metadata produced by Pi's two-dimensional output limit."""

    content: str
    truncated: bool
    truncated_by: str | None
    total_lines: int
    total_bytes: int
    output_lines: int
    output_bytes: int
    last_line_partial: bool
    max_lines: int
    max_bytes: int


@dataclass(frozen=True)
class PreparedBashOutput:
    """A bounded output tail awaiting an optional full-output path."""

    truncation: TruncationResult
    last_line_bytes: int

    def render(self, full_output_path: str | None, *, empty_text: str = "(no output)") -> str:
        """Render the exact truncation notice Pi exposes to the model."""
        result = self.truncation
        text = result.content or empty_text
        if not result.truncated:
            return text
        if not full_output_path:
            raise ValueError("full_output_path is required for truncated Bash output")

        start_line = result.total_lines - result.output_lines + 1
        end_line = result.total_lines
        if result.last_line_partial:
            notice = (
                f"Showing last {format_size(result.output_bytes)} of line {end_line} "
                f"(line is {format_size(self.last_line_bytes)}). Full output: {full_output_path}"
            )
        elif result.truncated_by == "lines":
            notice = f"Showing lines {start_line}-{end_line} of {result.total_lines}. Full output: {full_output_path}"
        else:
            notice = (
                f"Showing lines {start_line}-{end_line} of {result.total_lines} "
                f"({format_size(DEFAULT_MAX_BYTES)} limit). Full output: {full_output_path}"
            )
        return f"{text}\n\n[{notice}]"


@dataclass(frozen=True)
class BashResult:
    """Pi-compatible text plus the success state used by our agent loop."""

    text: str
    ok: bool
    truncation: TruncationResult


def bash_parameters() -> dict[str, Any]:
    """Return Pi's Bash input schema in provider-neutral JSON Schema form."""
    return {
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


def parse_bash_input(arguments: str) -> BashInput:
    """Perform the validation Pi receives from its TypeBox tool schema."""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise BashArgumentError(f"Tool arguments are not valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("command"), str):
        raise BashArgumentError("Tool arguments require a `command` string.")

    timeout = parsed.get("timeout")
    if timeout is not None:
        if isinstance(timeout, bool) or not isinstance(timeout, int | float):
            raise BashArgumentError("Invalid timeout: must be a finite number of seconds")
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise BashArgumentError("Invalid timeout: must be a finite number of seconds")
        if timeout > MAX_TIMEOUT_SECONDS:
            raise BashArgumentError(f"Invalid timeout: maximum is {MAX_TIMEOUT_SECONDS} seconds")
    return BashInput(parsed["command"], timeout)


def prepare_bash_output(content: str) -> PreparedBashOutput:
    """Apply Pi's Bash tail truncation before returning output to the model."""
    truncation = truncate_tail(content)
    last_line_bytes = len(content.rsplit("\n", 1)[-1].encode()) if content else 0
    return PreparedBashOutput(truncation, last_line_bytes)


def render_bash_result(
    output: PreparedBashOutput,
    *,
    full_output_path: str | None,
    exit_code: int,
    timed_out: bool,
    timeout_seconds: float,
) -> BashResult:
    """Match Pi's success, nonzero-exit, and timeout result text."""
    if timed_out:
        text = _append_status(
            output.render(full_output_path, empty_text=""),
            f"Command timed out after {timeout_seconds:g} seconds",
        )
        return BashResult(text, False, output.truncation)

    text = output.render(full_output_path)
    if exit_code != 0:
        return BashResult(_append_status(text, f"Command exited with code {exit_code}"), False, output.truncation)
    return BashResult(text, True, output.truncation)


def truncate_tail(
    content: str,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    """Keep the last complete lines that fit, as Pi does for Bash output."""
    total_bytes = len(content.encode())
    lines = _split_lines_for_counting(content)
    total_lines = len(lines)
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return TruncationResult(
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

    output_lines: list[str] = []
    output_bytes = 0
    truncated_by = "lines"
    last_line_partial = False
    for line in reversed(lines):
        if len(output_lines) >= max_lines:
            break
        line_bytes = len(line.encode()) + (1 if output_lines else 0)
        if output_bytes + line_bytes > max_bytes:
            truncated_by = "bytes"
            if not output_lines:
                partial = _truncate_utf8_from_end(line, max_bytes)
                output_lines.insert(0, partial)
                output_bytes = len(partial.encode())
                last_line_partial = True
            break
        output_lines.insert(0, line)
        output_bytes += line_bytes

    if len(output_lines) >= max_lines and output_bytes <= max_bytes:
        truncated_by = "lines"
    output_content = "\n".join(output_lines)
    return TruncationResult(
        output_content,
        True,
        truncated_by,
        total_lines,
        total_bytes,
        len(output_lines),
        len(output_content.encode()),
        last_line_partial,
        max_lines,
        max_bytes,
    )


def format_size(size: int) -> str:
    """Format a byte count the same way as Pi's truncation notice."""
    if size < 1_024:
        return f"{size}B"
    if size < 1_024 * 1_024:
        return f"{size / 1_024:.1f}KB"
    return f"{size / (1_024 * 1_024):.1f}MB"


def _split_lines_for_counting(content: str) -> list[str]:
    if not content:
        return []
    lines = content.split("\n")
    if content.endswith("\n"):
        lines.pop()
    return lines


def _truncate_utf8_from_end(value: str, max_bytes: int) -> str:
    encoded = value.encode()
    if len(encoded) <= max_bytes:
        return value
    return encoded[-max_bytes:].decode(errors="ignore")


def _append_status(text: str, status: str) -> str:
    return f"{text}\n\n{status}" if text else status
