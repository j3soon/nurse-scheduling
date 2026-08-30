"""Pydantic validation for the web frontend scheduling subset."""

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

from pydantic import model_validator
from typing_extensions import Self

from .loader import _load_yaml
from .models import (
    NurseSchedulingData,
    Person,
    ShiftAffinityPreference,
    ShiftCountPreference,
    ShiftRequestPreference,
    ShiftTypeRequirementsPreference,
    ShiftTypeSuccessionsPreference,
)


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


class _FrontendNurseSchedulingData(NurseSchedulingData):
    """Canonical schedule constrained to shapes editable by the web UI."""

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


def load_frontend_data(content: bytes) -> NurseSchedulingData:
    """Parse YAML with canonical validation and the frontend subset policy."""
    return _FrontendNurseSchedulingData.model_validate(_load_yaml(content))


def validate_frontend_data(data: NurseSchedulingData) -> NurseSchedulingData:
    """Apply the frontend subset policy to an already validated schedule."""
    return _FrontendNurseSchedulingData.model_validate(data.model_dump(mode="python"))
