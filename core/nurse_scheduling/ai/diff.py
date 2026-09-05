"""Structural differences between two schedules, for proposal review."""

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
from dataclasses import dataclass
from typing import Any, Literal

from .validation import format_schedule_location

MAX_DIFF_ENTRIES = 50
MAX_DIFF_VALUE_CHARS = 200

DiffKind = Literal["added", "removed", "changed"]


@dataclass(frozen=True)
class DiffEntry:
    """One rendered difference between two schedules."""

    kind: DiffKind
    location: str
    before: str
    after: str

    def render(self) -> str:
        if self.kind == "added":
            return f"- {self.location}: added {self.after}"
        if self.kind == "removed":
            return f"- {self.location}: removed {self.before}"
        return f"- {self.location}: {self.before} -> {self.after}"


@dataclass(frozen=True)
class ScheduleDiff:
    """A bounded list of the changes between two schedules."""

    entries: tuple[DiffEntry, ...] = ()
    omitted: int = 0

    def render(self) -> str:
        """Describe the changes as bounded text for review and tool results."""
        if not self.entries:
            return "No changes."
        lines = [entry.render() for entry in self.entries]
        if self.omitted:
            lines.append(f"- {self.omitted} further changes were not listed.")
        return "\n".join(lines)


def diff_schedules(before: Any, after: Any) -> ScheduleDiff:
    """Compare two parsed schedules and report what changed.

    Comparing the parsed documents rather than their text keeps the review
    independent of how the candidate was written, and reveals an entry the
    assistant dropped even though the result is still a valid schedule.
    """
    changes = _collect(before, after, ())
    kept = changes[:MAX_DIFF_ENTRIES]
    return ScheduleDiff(tuple(_render(change) for change in kept), len(changes) - len(kept))


def _collect(before: Any, after: Any, location: tuple[object, ...]) -> list[tuple[DiffKind, tuple, Any, Any]]:
    """Compare two schedule nodes and report the differences depth first."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return _collect_mapping(before, after, location)
    if isinstance(before, list) and isinstance(after, list):
        return _collect_sequence(before, after, location)
    return [("changed", location, before, after)]


def _collect_mapping(before: dict, after: dict, location: tuple[object, ...]) -> list[tuple]:
    """Report added, removed, and changed mapping members in a stable order."""
    changes: list[tuple] = []
    for key, value in before.items():
        if key not in after:
            changes.append(("removed", (*location, key), value, None))
        else:
            changes.extend(_collect(value, after[key], (*location, key)))
    changes.extend(("added", (*location, key), None, value) for key, value in after.items() if key not in before)
    return changes


def _collect_sequence(before: list, after: list, location: tuple[object, ...]) -> list[tuple]:
    """Report sequence edits without cascading when one entry is inserted or removed."""
    # Matching the shared prefix and suffix keeps a single insertion or removal
    # from rendering as a change to every following entry.
    prefix = 0
    while prefix < len(before) and prefix < len(after) and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < len(before) - prefix and suffix < len(after) - prefix and before[-1 - suffix] == after[-1 - suffix]:
        suffix += 1

    changes: list[tuple] = []
    middle_before = before[prefix : len(before) - suffix]
    middle_after = after[prefix : len(after) - suffix]
    for offset in range(min(len(middle_before), len(middle_after))):
        changes.extend(_collect(middle_before[offset], middle_after[offset], (*location, prefix + offset)))
    for offset in range(len(middle_after), len(middle_before)):
        changes.append(("removed", (*location, prefix + offset), middle_before[offset], None))
    for offset in range(len(middle_before), len(middle_after)):
        changes.append(("added", (*location, prefix + offset), None, middle_after[offset]))
    return changes


def _render(change: tuple[DiffKind, tuple, Any, Any]) -> DiffEntry:
    """Render one collected change with bounded values."""
    kind, location, before, after = change
    return DiffEntry(
        kind=kind,
        location=format_schedule_location(location),
        before="" if kind == "added" else _render_value(before),
        after="" if kind == "removed" else _render_value(after),
    )


def _render_value(value: Any) -> str:
    """Render one value as bounded JSON so diffs stay readable."""
    text = json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= MAX_DIFF_VALUE_CHARS:
        return text
    return text[: MAX_DIFF_VALUE_CHARS - 3] + "..."
