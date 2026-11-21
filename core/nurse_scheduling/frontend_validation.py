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

from datetime import date
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
from .utils import DATE_RANGE_SELECTOR_PATTERN, is_date_selector_shape

FRONTEND_DATE_REFERENCE_ERROR = "frontend_date_reference"


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


def _find_date_reference_error(data: dict[str, Any]) -> InitErrorDetails | None:
    """Find the first unsupported date reference, even in an incomplete payload."""

    def issue(value: Any, path: tuple[str | int, ...], message: str) -> InitErrorDetails:
        return InitErrorDetails(
            type=PydanticCustomError(FRONTEND_DATE_REFERENCE_ERROR, message),
            loc=path,
            input=value,
        )

    def find(value: Any, path: tuple[str | int, ...]) -> InitErrorDetails | None:
        if isinstance(value, list):
            for index, selector in enumerate(value):
                if error := find(selector, (*path, index)):
                    return error
        elif isinstance(value, str):
            if not value.isascii() and is_date_selector_shape(value):
                return issue(value, path, "Use ASCII digits (0-9) in dates")
            if DATE_RANGE_SELECTOR_PATTERN.match(value):
                return issue(
                    value, path, "Use individual dates or a named date group instead of a date range expression"
                )
        return None

    dates = data.get("dates")
    export = data.get("export")
    bounds = dates.get("range") if isinstance(dates, dict) else None
    if isinstance(bounds, dict):
        for field in ("startDate", "endDate"):
            value = bounds.get(field)
            if isinstance(value, str) and not value.isascii() and is_date_selector_shape(value):
                return issue(value, ("dates", "range", field), "Use ASCII digits (0-9) in dates")

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
            if path == ("dates", "groups"):
                group_id = entry.get("id")
                if isinstance(group_id, (str, int, date)) and is_date_selector_shape(str(group_id)):
                    return issue(
                        group_id,
                        (*path, index, "id"),
                        "Date group IDs cannot look like dates or date range expressions",
                    )
            for field in fields:
                if error := find(entry.get(field), (*path, index, field)):
                    return error
    return None


def _validate_frontend_payload(data: dict[str, Any]) -> ScheduleSpec:
    date_error = _find_date_reference_error(data)
    try:
        spec = _FrontendScheduleSpec.model_validate(data)
    except ValidationError as error:
        if date_error is None:
            raise
        # AI edits compare validation errors before and after a repair.
        # Keep preexisting errors visible alongside the date reference error.
        raise ValidationError.from_exception_data(error.title, [date_error, *error.errors()]) from error
    if date_error is not None:
        raise ValidationError.from_exception_data(_FrontendScheduleSpec.__name__, [date_error])
    return spec


def load_frontend_data(content: bytes) -> ScheduleSpec:
    """Parse YAML with backend Schedule Spec validation and the frontend subset policy."""
    return _validate_frontend_payload(_load_yaml(content, reject_aliases=True))


def validate_frontend_data(data: ScheduleSpec) -> ScheduleSpec:
    """Apply the frontend subset policy to an already validated Schedule Spec."""
    return _validate_frontend_payload(data.model_dump(mode="python"))
