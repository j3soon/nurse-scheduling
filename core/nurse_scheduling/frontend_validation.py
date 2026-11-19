"""Validate normalized web frontend state rather than raw import compatibility."""

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

from typing import Any

from pydantic import ValidationError, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError
from typing_extensions import Self

from .loader import _load_yaml
from .models import (
    Person,
    ScheduleSpec,
    ShiftAffinityPreference,
    ShiftCountPreference,
    ShiftRequestPreference,
    ShiftTypeRequirementsPreference,
    ShiftTypeSuccessionsPreference,
)
from .utils import DATE_RANGE_SELECTOR_PATTERN

FRONTEND_DATE_RANGE_ERROR = "frontend_date_range_expression"


def _require_string(value: Any, path: str) -> None:
    """Require an ID shape that the web frontend preserves exactly."""
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string for the web frontend")  # noqa: TRY004


def _require_flat_string_list(value: Any, path: str) -> None:
    """Require the flat string-reference lists used by frontend state."""
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list for the web frontend")  # noqa: TRY004
    if any(isinstance(item, list) for item in value):
        raise ValueError(f"{path} must not contain nested references for the web frontend")
    for index, item in enumerate(value):
        _require_string(item, f"{path}[{index}]")


class _FrontendScheduleSpec(ScheduleSpec):
    """Backend Schedule Spec format constrained to shapes editable by the web UI."""

    @model_validator(mode="after")
    def validate_frontend_subset(self) -> Self:
        for container_name, container in (("people", self.people), ("shiftTypes", self.shiftTypes)):
            for item_index, item in enumerate(container.items):
                path = f"{container_name}.items[{item_index}]"
                _require_string(item.id, f"{path}.id")
                if item.description is None:
                    raise ValueError(f"{path}.description is required by the web frontend")
                if isinstance(item, Person) and item.history is not None:
                    _require_flat_string_list(item.history, f"{path}.history")
            for group_index, group in enumerate(container.groups):
                path = f"{container_name}.groups[{group_index}]"
                _require_string(group.id, f"{path}.id")
                _require_flat_string_list(group.members, f"{path}.members")
                if group.description is None:
                    raise ValueError(f"{path}.description is required by the web frontend")

        for group_index, group in enumerate(self.dates.groups):
            path = f"dates.groups[{group_index}]"
            _require_string(group.id, f"{path}.id")
            _require_flat_string_list(group.members, f"{path}.members")
            if group.description is None:
                raise ValueError(f"{path}.description is required by the web frontend")

        for preference_index, preference in enumerate(self.preferences):
            path = f"preferences[{preference_index}]"
            if isinstance(preference, ShiftRequestPreference):
                _require_flat_string_list(preference.person, f"{path}.person")
                _require_flat_string_list(preference.date, f"{path}.date")
                _require_flat_string_list(preference.shiftType, f"{path}.shiftType")
                if len(preference.person) != 1:
                    raise ValueError(f"{path}.person must contain exactly one person for the web frontend")
                if len(preference.shiftType) != 1:
                    raise ValueError(f"{path}.shiftType must contain exactly one shift type for the web frontend")
            elif isinstance(preference, ShiftTypeSuccessionsPreference):
                _require_flat_string_list(preference.person, f"{path}.person")
                _require_flat_string_list(preference.pattern, f"{path}.pattern")
                _require_flat_string_list(preference.date, f"{path}.date")
            elif isinstance(preference, ShiftTypeRequirementsPreference):
                _require_flat_string_list(preference.shiftType, f"{path}.shiftType")
                _require_flat_string_list(preference.qualifiedPeople, f"{path}.qualifiedPeople")
                _require_flat_string_list(preference.date, f"{path}.date")
            elif isinstance(preference, ShiftCountPreference):
                _require_flat_string_list(preference.person, f"{path}.person")
                _require_flat_string_list(preference.countDates, f"{path}.countDates")
                _require_flat_string_list(preference.countShiftTypes, f"{path}.countShiftTypes")
                if isinstance(preference.expression, list):
                    raise ValueError(  # noqa: TRY004
                        f"{path}.expression must be a scalar for the web frontend"
                    )
                if isinstance(preference.target, list):
                    raise ValueError(f"{path}.target must be a scalar for the web frontend")  # noqa: TRY004
            elif isinstance(preference, ShiftAffinityPreference):
                _require_flat_string_list(preference.date, f"{path}.date")
                _require_flat_string_list(preference.people1, f"{path}.people1")
                _require_flat_string_list(preference.people2, f"{path}.people2")
                _require_flat_string_list(preference.shiftTypes, f"{path}.shiftTypes")

        for rule_index, rule in enumerate(self.export.formatting):
            for field_name in ("people", "dates", "shiftTypes"):
                if hasattr(rule, field_name):
                    _require_flat_string_list(
                        getattr(rule, field_name),
                        f"export.formatting[{rule_index}].{field_name}",
                    )
        for rule_index, rule in enumerate(self.export.extraColumns):
            _require_flat_string_list(rule.countShiftTypes, f"export.extraColumns[{rule_index}].countShiftTypes")
            _require_flat_string_list(rule.countDates, f"export.extraColumns[{rule_index}].countDates")
        for rule_index, rule in enumerate(self.export.extraRows):
            _require_flat_string_list(rule.countShiftTypes, f"export.extraRows[{rule_index}].countShiftTypes")
            _require_flat_string_list(rule.countPeople, f"export.extraRows[{rule_index}].countPeople")
        return self


def _validate_frontend_payload(data: dict[str, Any]) -> ScheduleSpec:
    # Check range expressions before backend validation so they also fail on
    # an incomplete Schedule Spec that the AI can otherwise continue editing.
    group_ids: set[str] = set()

    def check(value: Any, path: tuple[str | int, ...]) -> None:
        if isinstance(value, list):
            for index, selector in enumerate(value):
                check(selector, (*path, index))
        elif isinstance(value, str) and value not in group_ids and DATE_RANGE_SELECTOR_PATTERN.match(value):
            raise ValidationError.from_exception_data(
                _FrontendScheduleSpec.__name__,
                [
                    InitErrorDetails(
                        type=PydanticCustomError(
                            FRONTEND_DATE_RANGE_ERROR,
                            "Use individual dates or a named date group instead of a date range expression",
                        ),
                        loc=path,
                        input=value,
                    )
                ],
            )

    dates = data.get("dates")
    export = data.get("export")
    sections = (
        (("dates", "groups"), dates.get("groups") if isinstance(dates, dict) else None, ("members",)),
        (("preferences",), data.get("preferences"), ("date", "countDates")),
        (("export", "formatting"), export.get("formatting") if isinstance(export, dict) else None, ("dates",)),
        (("export", "extraColumns"), export.get("extraColumns") if isinstance(export, dict) else None, ("countDates",)),
    )
    for path, entries, fields in sections:
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            for field in fields:
                check(entry.get(field), (*path, index, field))
            if path == ("dates", "groups") and isinstance(group_id := entry.get("id"), str):
                group_ids.add(group_id)
    return _FrontendScheduleSpec.model_validate(data)


def load_frontend_data(content: bytes) -> ScheduleSpec:
    """Parse YAML with backend Schedule Spec validation and the frontend subset policy."""
    return _validate_frontend_payload(_load_yaml(content, reject_aliases=True))


def validate_frontend_data(data: ScheduleSpec) -> ScheduleSpec:
    """Apply the frontend subset policy to an already validated Schedule Spec."""
    return _validate_frontend_payload(data.model_dump(mode="python"))
