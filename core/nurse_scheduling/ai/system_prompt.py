"""Assemble the ordered system prompt shared by production and evaluations."""

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

# This code is mostly AI generated.

import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

PROMPT_STEPS_PATH = Path(__file__).with_name("prompts") / "system-steps.json"
PROMPT_DIRECTORY = PROMPT_STEPS_PATH.parent


def load_system_prompt_entries(path: Path = PROMPT_STEPS_PATH) -> tuple[dict[str, Any], ...]:
    """Read the ordered manifest and check its file references."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise TypeError("System prompt steps must be a JSON list")
    entries = tuple(raw)
    ids: set[str] = set()
    files: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise TypeError("Each system prompt step needs an ID and Markdown file")
        identifier = entry["id"]
        file = entry.get("file")
        if not identifier or identifier in ids or not isinstance(file, str) or not file:
            raise ValueError("System prompt step IDs and files must be nonempty and unique")
        fragment = PurePosixPath(file)
        if fragment.is_absolute() or ".." in fragment.parts or fragment.suffix != ".md" or file in files:
            raise ValueError(f"Invalid or repeated system prompt file: {file}")
        ids.add(identifier)
        files.add(file)
    return entries


def load_system_prompt_sections(entries: Sequence[dict[str, Any]] | None = None) -> tuple[str, ...]:
    """Read model instructions without repository provenance or final newlines."""
    selected = load_system_prompt_entries() if entries is None else entries
    sections = tuple(_section_text(PROMPT_DIRECTORY / entry["file"]) for entry in selected)
    if any(not section for section in sections):
        raise ValueError("System prompt sections must be nonempty")
    return sections


def _section_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    header, separator, body = text.partition("-->")
    if text.startswith("<!--") and separator and "SPDX-License-Identifier:" in header:
        text = body.lstrip("\n")
        marker = "<!-- This file is mostly AI generated. -->"
        if text.startswith(marker):
            text = text[len(marker) :].lstrip("\n")
    return text.rstrip("\n")


def compose_system_prompt(step: int | None = None, *, omit: int | None = None) -> str:
    """Compose the full prompt or an evaluation prefix with one optional omission."""
    sections = load_system_prompt_sections()
    count = len(sections) if step is None else step
    if count < 0 or count > len(sections):
        raise ValueError(f"Prompt step must be between 0 and {len(sections)}")
    if omit is not None and (omit < 1 or omit > count):
        raise ValueError("Omitted section must be included in the selected prompt step")
    return "\n\n".join(section for index, section in enumerate(sections[:count], 1) if index != omit)
