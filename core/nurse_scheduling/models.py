"""Pydantic data models for the nurse scheduling schema."""

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

import datetime
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from . import utils
from .constants import ALL, MAP_DATE_KEYWORD_TO_FILTER, MAP_WEEKDAY_TO_STR, OFF

AT_MOST_ONE_SHIFT_PER_DAY = "at most one shift per day"
SHIFT_TYPE_REQUIREMENT = "shift type requirement"
SHIFT_REQUEST = "shift request"
SHIFT_TYPE_SUCCESSIONS = "shift type successions"
SHIFT_COUNT = "shift count"
SHIFT_AFFINITY = "shift affinity"
SUPPORTED_SHIFT_COUNT_EXPRESSIONS = frozenset({"|x - T|^2", "x >= T", "x <= T", "x > T", "x < T", "x = T"})


def validate_weight(weight: float) -> int | float:
    """Validate that float weights can only be positive or negative infinity."""
    if isinstance(weight, float) and weight != math.inf and weight != -math.inf:
        raise ValueError("Float weights can only be positive infinity or negative infinity.")
    return weight


# Base models
class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None
    history: list[str] | None = None


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startDate: datetime.date
    endDate: datetime.date


class PeopleGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    members: list[int | str]  # Can reference person IDs or other group IDs


class ShiftType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None


class ShiftTypeGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    members: list[int | str]  # Can reference shift type IDs or other group IDs


class DateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    members: list[int | str | datetime.date]  # Can reference date IDs, group IDs, or date objects


class PeopleContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Person]
    groups: list[PeopleGroup] = Field(default_factory=list)


class ShiftTypesContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ShiftType]
    groups: list[ShiftTypeGroup] = Field(default_factory=list)


class DateContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    range: DateRange
    items: list[datetime.date] = Field(default_factory=list)  # Automatically generated from range
    groups: list[DateGroup] = Field(default_factory=list)


class BaseExportFormattingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str | None = None
    backgroundColor: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    bottomBorderColor: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    rightBorderColor: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    fontColor: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None


class ExportPersonFormattingRule(BaseExportFormattingRule):
    type: Literal["row", "people header", "history"]
    people: list[int | str]


class ExportDateFormattingRule(BaseExportFormattingRule):
    type: Literal["column", "date header"]
    dates: list[int | str]


class ExportHistoryHeaderFormattingRule(BaseExportFormattingRule):
    type: Literal["history header"]


class ExportPreferenceCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    types: list[Literal["shift request"]]
    requestShape: (
        list[
            Literal[
                "person-item-to-date-item",
                "people-group-to-date-item",
                "person-item-to-date-group",
                "people-group-to-date-group",
                "ALL",
            ]
        ]
        | None
    ) = None
    satisfied: bool | None = None
    weightRange: list[int | float] | None = None


class ExportFormattingCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preference: ExportPreferenceCondition


class ExportFormattingNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class ExportCellFormattingRule(BaseExportFormattingRule):
    type: Literal["cell"]
    appendText: str | None = None
    note: ExportFormattingNote | None = None
    people: list[int | str]
    dates: list[int | str]
    shiftTypes: list[int | str]
    when: ExportFormattingCondition | None = None


ExportFormattingRule = Annotated[
    ExportPersonFormattingRule
    | ExportDateFormattingRule
    | ExportHistoryHeaderFormattingRule
    | ExportCellFormattingRule,
    Field(discriminator="type"),
]


class ExportExtraColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str | None = None
    rightBorderColor: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    type: Annotated[str, Field(pattern=r"^count$")]
    header: str
    countShiftTypes: list[int | str]
    countShiftTypeCoefficients: list[tuple[str, int]] | None = None
    countDates: list[int | str]


class ExportExtraRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str | None = None
    bottomBorderColor: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None
    type: Annotated[str, Field(pattern=r"^count$")]
    header: str
    countShiftTypes: list[int | str]
    countPeople: list[int | str]


class ExportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formatting: list[ExportFormattingRule] = Field(default_factory=list)
    extraColumns: list[ExportExtraColumn] = Field(default_factory=list)
    extraRows: list[ExportExtraRow] = Field(default_factory=list)


class BasePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str


class ShiftRequestPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_REQUEST}$")] = SHIFT_REQUEST
    description: str | None = None
    person: (int | str) | list[int | str]  # Single person/group ID or list
    date: (int | str | datetime.date) | list[int | str | datetime.date]  # Single date or list of dates
    shiftType: str | list[str]  # Single shift type ID or list
    weight: int | float = Field(default=1)  # For float can only be .inf or -.inf

    @field_validator("weight")
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)


class ShiftTypeSuccessionsPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_TYPE_SUCCESSIONS}$")] = SHIFT_TYPE_SUCCESSIONS
    description: str | None = None
    person: (int | str) | list[int | str]  # Single person/group ID or list
    pattern: list[str | list[str]]  # List of shift type IDs or nested patterns
    date: (int | str | datetime.date) | list[int | str | datetime.date] | None = None  # Single date or list of dates
    weight: int | float = Field(default=1)  # For float can only be .inf or -.inf

    @field_validator("weight")
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)


class MaxOneShiftPerDayPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{AT_MOST_ONE_SHIFT_PER_DAY}$")] = AT_MOST_ONE_SHIFT_PER_DAY
    description: str | None = None


class ShiftTypeRequirementsPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_TYPE_REQUIREMENT}$")] = SHIFT_TYPE_REQUIREMENT
    description: str | None = None
    # Single shift type ID, a flat list of independent shift type IDs, or
    # nested aggregate groups of shift type IDs.
    shiftType: str | list[str | list[str]]
    shiftTypeCoefficients: list[tuple[str, int]] | None = None
    requiredNumPeople: int
    # None and the reserved "ALL" selector both mean all people. The frontend
    # intentionally normalizes implicit all-people values to explicit "ALL".
    qualifiedPeople: (int | str) | list[int | str] | None = None
    preferredNumPeople: int | None = None  # Preferred number of people for each shift type
    # None and the reserved "ALL" selector both mean all dates. The frontend
    # intentionally normalizes implicit all-date values to explicit "ALL".
    date: (int | str | datetime.date) | list[int | str | datetime.date] | None = None  # Single date or list of dates
    weight: int | float = Field(default=-1)  # For float can only be .inf or -.inf

    @field_validator("weight")
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)


class ShiftCountPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_COUNT}$")] = SHIFT_COUNT
    description: str | None = None
    person: (int | str) | list[int | str]  # Single person/group ID or list
    countDates: (int | str | datetime.date) | list[int | str | datetime.date]  # Single date or list of dates
    countShiftTypes: str | list[str]  # Single shift type ID or list
    countShiftTypeCoefficients: list[tuple[str, int]] | None = None
    expression: str | list[str]  # Single mathematical expression or list of mathematical expressions
    target: int | list[int]  # Single target value or list of target values
    weight: int | float = Field(default=-1)  # For float can only be .inf or -.inf

    @field_validator("weight")
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)


class ShiftAffinityPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_AFFINITY}$")] = SHIFT_AFFINITY
    description: str | None = None
    date: (int | str | datetime.date) | list[int | str | datetime.date]  # Single date or list of dates
    people1: list[int | str | list[int | str]]  # First person ID list or nested
    people2: list[int | str | list[int | str]]  # Second person ID list or nested
    shiftTypes: list[str | list[str]]  # Shift type ID list or nested
    weight: int | float = Field(default=1)  # For float can only be .inf or -.inf

    @field_validator("weight")
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)


class NurseSchedulingData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appVersion: str | None = None
    apiVersion: str
    description: str | None = None
    dates: DateContainer
    people: PeopleContainer
    shiftTypes: ShiftTypesContainer
    preferences: list[
        MaxOneShiftPerDayPreference
        | ShiftRequestPreference
        | ShiftTypeSuccessionsPreference
        | ShiftTypeRequirementsPreference
        | ShiftCountPreference
        | ShiftAffinityPreference
    ]
    export: ExportConfig = Field(default_factory=ExportConfig)

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        # Validate preferences
        required_prefs = {AT_MOST_ONE_SHIFT_PER_DAY}
        found_prefs = {pref.type for pref in self.preferences}
        missing = required_prefs - found_prefs
        if missing:
            raise ValueError(f"Missing required preferences: {missing}")

        # Validate dates
        if self.dates.range.endDate < self.dates.range.startDate:
            raise ValueError("enddate must be after or equal to startdate")

        # Validate duplicate IDs and reserved IDs
        shift_type_reserved_ids = {k.upper() for k in {ALL, OFF}}
        shift_type_ids = set()
        shift_type_group_ids = set()
        for shift_type in self.shiftTypes.items:
            if shift_type.id in shift_type_ids:
                raise ValueError(f"Duplicated shift type ID: {shift_type.id!r}")
            if str(shift_type.id).upper() in shift_type_reserved_ids:
                raise ValueError(
                    f"Shift type ID {shift_type.id!r} cannot be one of the reserved values: {shift_type_reserved_ids}"
                )
            shift_type_ids.add(shift_type.id)
        for group in self.shiftTypes.groups:
            if group.id in shift_type_ids or group.id in shift_type_group_ids:
                raise ValueError(f"Duplicated shift type group (or shift type) ID: {group.id!r}")
            if str(group.id).upper() in shift_type_reserved_ids:
                raise ValueError(
                    f"Shift type group ID {group.id!r} cannot be one of the reserved values: {shift_type_reserved_ids}"
                )
            shift_type_group_ids.add(group.id)

        # Validate duplicate IDs and reserved IDs
        people_reserved_ids = {k.upper() for k in {ALL}}
        person_and_group_ids = set()
        for person in self.people.items:
            if person.id in person_and_group_ids:
                raise ValueError(f"Duplicated person ID: {person.id!r}")
            if str(person.id).upper() in people_reserved_ids:
                raise ValueError(f"Person ID {person.id!r} cannot be one of the reserved values: {people_reserved_ids}")
            for history_shift_type_id in person.history or []:
                if history_shift_type_id == ALL:
                    raise ValueError(f"History must not include 'ALL', but got {history_shift_type_id!r}")
                if history_shift_type_id in shift_type_group_ids:
                    raise ValueError(f"History must not include group ID, but got {history_shift_type_id!r}")
                if history_shift_type_id != OFF and history_shift_type_id not in shift_type_ids:
                    raise ValueError(f"Unknown shift type ID in history: {history_shift_type_id!r}")
            person_and_group_ids.add(person.id)
        for group in self.people.groups:
            if group.id in person_and_group_ids:
                raise ValueError(f"Duplicated people group (or person) ID: {group.id!r}")
            if str(group.id).upper() in people_reserved_ids:
                raise ValueError(
                    f"People group ID {group.id!r} cannot be one of the reserved values: {people_reserved_ids}"
                )
            person_and_group_ids.add(group.id)

        # Validate dates
        if self.dates.items:
            raise ValueError("dates.items is not allowed since it is automatically generated from dates.range")
        date_reserved_ids = {k.upper() for k in MAP_WEEKDAY_TO_STR} | {k.upper() for k in MAP_DATE_KEYWORD_TO_FILTER}
        date_group_ids = set()
        for group in self.dates.groups:
            if group.id in date_group_ids:
                raise ValueError(f"Duplicated date group ID: {group.id!r}")
            if str(group.id).upper() in date_reserved_ids:
                raise ValueError(
                    f"Date group ID {group.id!r} cannot be one of the reserved values: {date_reserved_ids}"
                )
            if (
                re.match(r"^\d{1,2}$", group.id)
                or re.match(r"^(\d{2})-(\d{2})$", group.id)
                or re.match(r"^(\d{4})-(\d{2})-(\d{2})$", group.id)
            ):
                raise ValueError(f"Date group ID {group.id!r} must not be in the format of YYYY-MM-DD, MM-DD, or D")
            date_group_ids.add(group.id)

        _validate_schedule_semantics(self)
        return self


def _build_reference_map(item_ids, groups, reserved, reference_name):
    """Expand ordered item and group IDs into concrete reference sets."""
    reference_map = {item_id: {item_id} for item_id in item_ids}
    reference_map.update(reserved)
    for group in groups:
        expanded = set()
        for member in group.members:
            if member not in reference_map:
                raise ValueError(f"Unknown {reference_name} ID: {member}")
            expanded.update(reference_map[member])
        reference_map[group.id] = expanded
    return reference_map


def _build_date_map(data: NurseSchedulingData):
    """Build the date selector map used by canonical reference validation."""
    date_range = data.dates.range
    n_days = (date_range.endDate - date_range.startDate).days + 1
    date_map = {str(date_range.startDate + datetime.timedelta(days=index)): [index] for index in range(n_days)}
    for keyword, predicate in MAP_DATE_KEYWORD_TO_FILTER.items():
        date_map[keyword] = [
            index for index in range(n_days) if predicate(date_range.startDate + datetime.timedelta(days=index))
        ]
    for weekday_index, keyword in enumerate(MAP_WEEKDAY_TO_STR):
        date_map[keyword] = [
            index
            for index in range(n_days)
            if (date_range.startDate + datetime.timedelta(days=index)).weekday() == weekday_index
        ]
    for group in data.dates.groups:
        expanded = set()
        for member in group.members:
            expanded.update(utils.parse_dates(member, date_map, date_range))
        date_map[group.id] = sorted(expanded)
    return date_map


def _iter_leaf_references(value):
    """Yield scalar IDs from flat or nested reference lists."""
    if isinstance(value, list):
        for item in value:
            yield from _iter_leaf_references(item)
        return
    yield value


def _validate_nested_references(value, reference_map, reference_name):
    """Reject unknown IDs while preserving supported nested reference shapes."""
    for item in _iter_leaf_references(value):
        if item not in reference_map:
            raise ValueError(f"Unknown {reference_name} ID: {item}")


def _expanded_shift_groups(value, shift_map):
    """Normalize shift requirement selectors into concrete shift sets."""
    selectors = value if isinstance(value, list) else [value]
    groups = []
    for selector in selectors:
        members = selector if isinstance(selector, list) else [selector]
        groups.append(set().union(*(shift_map[member] for member in members)))
    return groups


def _validate_coefficients(entries, selected, shift_map, label, selection_name):
    """Validate coefficient references, coverage, values, and overlap."""
    covered = set()
    for shift_type_id, coefficient in entries or []:
        if coefficient < 1:
            raise ValueError(f"{label} for '{shift_type_id}' must be at least 1.")
        if shift_type_id not in shift_map:
            raise ValueError(f"Unknown shift type ID: {shift_type_id}")
        expanded = shift_map[shift_type_id]
        if not expanded.issubset(selected):
            raise ValueError(f"{label} for '{shift_type_id}' must be covered by {selection_name}.")
        if covered.intersection(expanded):
            raise ValueError(f"Duplicate {label.lower()} for '{shift_type_id}'.")
        covered.update(expanded)


def _validate_schedule_semantics(data: NurseSchedulingData) -> None:
    """Validate canonical scheduling semantics after Pydantic field parsing."""
    if data.apiVersion != "alpha":
        raise ValueError(f"Unsupported API version: {data.apiVersion}")

    shift_ids = [item.id for item in data.shiftTypes.items]
    shift_map = _build_reference_map(
        shift_ids,
        data.shiftTypes.groups,
        {ALL: set(shift_ids), OFF: {OFF}},
        "shift type",
    )
    people_ids = [item.id for item in data.people.items]
    people_map = _build_reference_map(
        people_ids,
        data.people.groups,
        {ALL: set(people_ids)},
        "person",
    )
    date_map = _build_date_map(data)

    for preference in data.preferences:
        if isinstance(preference, ShiftRequestPreference):
            utils.parse_pids(preference.person, people_map)
            utils.parse_dates(preference.date, date_map, data.dates.range)
            utils.parse_sids(preference.shiftType, shift_map)
        elif isinstance(preference, ShiftTypeSuccessionsPreference):
            utils.parse_pids(preference.person, people_map)
            if not preference.pattern:
                raise ValueError("Pattern must not be empty")
            _validate_nested_references(preference.pattern, shift_map, "shift type")
            if preference.date is not None:
                utils.parse_dates(preference.date, date_map, data.dates.range)
        elif isinstance(preference, ShiftTypeRequirementsPreference):
            _validate_nested_references(preference.shiftType, shift_map, "shift type")
            shift_groups = _expanded_shift_groups(preference.shiftType, shift_map)
            if not shift_groups or any(not group for group in shift_groups):
                raise ValueError(f"Non-empty shift types are required, but got {preference.shiftType}")
            if any(OFF in group for group in shift_groups):
                raise ValueError("'OFF' is not allowed in shift type requirement preferences.")
            if preference.shiftTypeCoefficients and len(shift_groups) != 1:
                raise ValueError(
                    "Shift type requirement coefficients are only supported when shiftType normalizes to one "
                    "requirement group."
                )
            _validate_coefficients(
                preference.shiftTypeCoefficients,
                set().union(*shift_groups),
                shift_map,
                "Shift type requirement coefficient",
                "shiftType",
            )
            if preference.qualifiedPeople is not None:
                utils.parse_pids(preference.qualifiedPeople, people_map)
            if preference.date is not None:
                utils.parse_dates(preference.date, date_map, data.dates.range)
        elif isinstance(preference, ShiftCountPreference):
            utils.parse_pids(preference.person, people_map)
            utils.parse_dates(preference.countDates, date_map, data.dates.range)
            selected_shift_types = set(utils.parse_sids(preference.countShiftTypes, shift_map))
            if not selected_shift_types:
                raise ValueError(f"Non-empty count shift types are required, but got {preference.countShiftTypes}")
            _validate_coefficients(
                preference.countShiftTypeCoefficients,
                selected_shift_types,
                shift_map,
                "Shift count coefficient",
                "countShiftTypes",
            )
            expressions = utils.ensure_list(preference.expression)
            targets = utils.ensure_list(preference.target)
            if len(expressions) != len(targets):
                raise ValueError(
                    f"Number of expressions ({len(expressions)}) must match number of targets ({len(targets)})"
                )
            if not expressions:
                raise ValueError("Expression must not be empty")
            for expression in expressions:
                if expression not in SUPPORTED_SHIFT_COUNT_EXPRESSIONS:
                    raise ValueError(
                        f"Unsupported expression: {expression}. "
                        f"Supported expressions are: {sorted(SUPPORTED_SHIFT_COUNT_EXPRESSIONS)}"
                    )
                if expression == "|x - T|^2":
                    if preference.weight == math.inf:
                        raise ValueError(f"'.inf' weights are not allowed for shift count with '{expression}'.")
                    if preference.weight != -math.inf and preference.weight > 0:
                        raise ValueError(f"Weight must be non-positive for shift count with '{expression}'.")
            for target in targets:
                if target < 0:
                    raise ValueError(f"Target must be non-negative, but got {target}")
        elif isinstance(preference, ShiftAffinityPreference):
            utils.parse_dates(preference.date, date_map, data.dates.range)
            if not preference.people1 or not preference.people2:
                raise ValueError("Shift affinity people selections must not be empty")
            if not preference.shiftTypes:
                raise ValueError("Shift affinity shift types must not be empty")
            _validate_nested_references(preference.people1, people_map, "person")
            _validate_nested_references(preference.people2, people_map, "person")
            _validate_nested_references(preference.shiftTypes, shift_map, "shift type")

    _validate_export_semantics(data, people_map, shift_map, date_map)


def _validate_export_semantics(data, people_map, shift_map, date_map):
    """Validate export references and options against the canonical schedule."""
    for rule in data.export.formatting:
        if hasattr(rule, "people"):
            for target in rule.people:
                if target not in people_map:
                    raise ValueError(
                        f"Invalid person identifier '{target}' in export formatting rule with type '{rule.type}'"
                    )
        if hasattr(rule, "dates"):
            utils.parse_dates(rule.dates, date_map, data.dates.range)
        if hasattr(rule, "shiftTypes"):
            for target in rule.shiftTypes:
                if target not in shift_map:
                    raise ValueError(
                        f"Invalid shift type identifier '{target}' in export formatting rule with type 'cell'"
                    )
        if isinstance(rule, ExportCellFormattingRule) and rule.when:
            weight_range = rule.when.preference.weightRange
            if weight_range is not None and len(weight_range) != 2:
                raise ValueError("export formatting preference weightRange must contain exactly two values")
            if weight_range is not None and weight_range[0] > weight_range[1]:
                raise ValueError(
                    "export formatting preference weightRange minimum must be less than or equal to maximum"
                )

    for rule in data.export.extraColumns:
        selected = set(utils.parse_sids(rule.countShiftTypes, shift_map))
        utils.parse_dates(rule.countDates, date_map, data.dates.range)
        _validate_coefficients(
            rule.countShiftTypeCoefficients,
            selected,
            shift_map,
            "Export extra column coefficient",
            "countShiftTypes",
        )
    for rule in data.export.extraRows:
        utils.parse_sids(rule.countShiftTypes, shift_map)
        utils.parse_pids(rule.countPeople, people_map)
