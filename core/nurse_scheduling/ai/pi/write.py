"""Python port of Pi's model-facing complete-file write behavior."""

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

# Adapted from Pi's packages/coding-agent/src/core/tools/write.ts
# at e266507b606b9552fa277252644054afd4384b11. Pi's MIT license is in LICENSE.
# This code is mostly AI generated.

import json
from dataclasses import dataclass
from typing import Any

from .bash import UPSTREAM_COMMIT

WRITE_TOOL = "write"
WRITE_PROMPT_SNIPPET = "Create or overwrite files"
WRITE_PROMPT_GUIDELINE = "Use write only for new files or complete rewrites."
UPSTREAM_SOURCE = (
    f"https://github.com/earendil-works/pi/blob/{UPSTREAM_COMMIT}/packages/coding-agent/src/core/tools/write.ts"
)
WRITE_TOOL_DESCRIPTION = (
    "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. "
    "Automatically creates parent directories."
)


class WriteArgumentError(ValueError):
    """The model supplied arguments outside Pi's write schema."""


@dataclass(frozen=True)
class WriteInput:
    """Validated input for one Pi-compatible write call."""

    path: str
    content: str


def write_parameters() -> dict[str, Any]:
    """Return Pi's write input schema in provider-neutral JSON Schema form."""
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write (relative or absolute)"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["path", "content"],
    }


def parse_write_input(arguments: str) -> WriteInput:
    """Perform the validation Pi receives from its TypeBox tool schema."""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise WriteArgumentError(f"Tool arguments are not valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("path"), str):
        raise WriteArgumentError("Tool arguments require a `path` string.")
    if not isinstance(parsed.get("content"), str):
        raise WriteArgumentError("Tool arguments require a `content` string.")
    return WriteInput(parsed["path"], parsed["content"])


def render_write_result(path: str) -> str:
    """Render Pi's successful write result."""
    return f"Successfully wrote to {path}"
