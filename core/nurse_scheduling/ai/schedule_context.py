"""Compact schedule context for AI prompts."""

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

from collections.abc import Iterable
from typing import Any

from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from .candidate import SCHEDULE_FILENAME

MAX_SUMMARY_IDS = 20
_GROUPED_SECTIONS = ("people", "dates", "shiftTypes")


def describe_schedule(schedule_text: str) -> str:
    """Summarize schedule shape without copying the working document."""
    line_count = len(schedule_text.splitlines())
    try:
        schedule = _load_yaml(schedule_text.encode("utf-8"))
    except (YAMLError, TypeError, ValueError):
        return f"{SCHEDULE_FILENAME} is {line_count} lines and does not currently parse."

    counts = [
        f"{_count(schedule, 'people')} people",
        f"{_count(schedule, 'shiftTypes')} shift types",
        f"{len(_as_list(schedule.get('preferences')))} preferences",
    ]
    summary = f"{SCHEDULE_FILENAME} is {line_count} lines: {', '.join(counts)}."

    date_range = _section(schedule, "dates").get("range")
    if isinstance(date_range, dict) and date_range.get("startDate") and date_range.get("endDate"):
        summary += f" Dates run from {date_range['startDate']} to {date_range['endDate']}."
    date_items = _count(schedule, "dates")
    if date_items:
        summary += f" {date_items} dates are listed individually."

    groups = [f"{name} {_group_ids(schedule, name)}" for name in _GROUPED_SECTIONS if _group_ids(schedule, name)]
    if groups:
        summary += f"\nGroup ids: {'; '.join(groups)}."
    return summary


def _count(schedule: Any, name: str) -> int:
    return len(_as_list(_section(schedule, name).get("items")))


def _group_ids(schedule: Any, name: str) -> str:
    return _bounded_ids(
        str(group["id"])
        for group in _as_list(_section(schedule, name).get("groups"))
        if isinstance(group, dict) and "id" in group
    )


def _bounded_ids(values: Iterable[str]) -> str:
    ids = list(values)
    if len(ids) > MAX_SUMMARY_IDS:
        return f"{', '.join(ids[:MAX_SUMMARY_IDS])} and {len(ids) - MAX_SUMMARY_IDS} more"
    return ", ".join(ids)


def _section(schedule: Any, name: str) -> dict[str, Any]:
    section = schedule.get(name) if isinstance(schedule, dict) else None
    return section if isinstance(section, dict) else {}


def _as_list(node: Any) -> list[Any]:
    return node if isinstance(node, list) else []
