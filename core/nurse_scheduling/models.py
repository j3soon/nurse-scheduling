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
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator
from typing_extensions import Self

from . import utils
from .constants import ALL, MAP_DATE_KEYWORD_TO_FILTER, MAP_WEEKDAY_TO_STR, OFF, OFF_sid

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

    @model_validator(mode="before")
    @classmethod
    def validate_cell_only_fields(cls, data):
        """Keep cell-only field errors actionable before extra-field rejection."""
        if isinstance(data, dict) and data.get("type") != "cell":
            if data.get("when") is not None:
                raise ValueError("export formatting 'when' is only supported for rules with type 'cell'")
            if data.get("appendText") is not None or data.get("note") is not None:
                raise ValueError("export formatting annotations are only supported for rules with type 'cell'")
        return data


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


class _FrozenMapping(Mapping):
    """Fast, pickle-safe mapping that rejects public mutation."""

    __slots__ = ("_data",)

    def __init__(self, data):
        object.__setattr__(self, "_data", MappingProxyType(dict(data)))

    def __setattr__(self, _name, _value):
        raise TypeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, _name):
        raise TypeError(f"{type(self).__name__} is immutable")

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def copy(self):
        return self

    def __copy__(self):
        return self

    def __deepcopy__(self, _memo):
        return self

    def __reduce__(self):
        return type(self), (dict(self._data),)


@dataclass(frozen=True)
class CompiledShiftRequestDateTarget:
    """Concrete dates and original selector shape for one request target."""

    dates: tuple[int, ...]
    request_shape: str


@dataclass(frozen=True)
class CompiledShiftRequest:
    """Resolved selectors used to build and export a shift request."""

    people: tuple[int, ...]
    dates: tuple[int, ...]
    shift_types: tuple[int, ...]
    date_targets: tuple[CompiledShiftRequestDateTarget, ...]
    requested_shift_type: str


@dataclass(frozen=True)
class CompiledPatternElement:
    """One resolved succession pattern element."""

    shift_types: tuple[int, ...]
    matches_all_working_shifts: bool


@dataclass(frozen=True)
class CompiledShiftTypeSuccessions:
    """Resolved selectors used by a succession preference."""

    people: tuple[int, ...]
    dates: tuple[int, ...]
    date_set: frozenset[int]  # Same dates optimized for succession window membership checks.
    pattern: tuple[CompiledPatternElement, ...]


@dataclass(frozen=True)
class CompiledShiftTypeRequirements:
    """Resolved staffing equations and optional eligibility selector."""

    dates: tuple[int, ...]
    shift_type_groups: tuple[tuple[int, ...], ...]
    coefficients: tuple[tuple[int, int], ...]
    qualified_people: tuple[int, ...] | None


@dataclass(frozen=True)
class CompiledShiftCount:
    """Resolved inputs used by a shift count preference."""

    people: tuple[int, ...]
    dates: tuple[int, ...]
    shift_types: tuple[int, ...]
    coefficients: tuple[tuple[int, int], ...]
    expressions: tuple[str, ...]
    targets: tuple[int, ...]


@dataclass(frozen=True)
class CompiledShiftAffinity:
    """Resolved selector groups used by a shift affinity preference."""

    dates: tuple[int, ...]
    people1_groups: tuple[tuple[int, ...], ...]
    people2_groups: tuple[tuple[int, ...], ...]
    shift_type_groups: tuple[tuple[int, ...], ...]


CompiledPreference = (
    CompiledShiftRequest
    | CompiledShiftTypeSuccessions
    | CompiledShiftTypeRequirements
    | CompiledShiftCount
    | CompiledShiftAffinity
    | None
)


@dataclass(frozen=True)
class CompiledExportFormattingRule:
    """Resolved selectors for one export formatting rule."""

    people: tuple[int, ...] = ()
    dates: tuple[int, ...] = ()
    shift_types: tuple[int, ...] = ()


@dataclass(frozen=True)
class CompiledExportExtraColumn:
    """Resolved selectors and coefficients for one extra column."""

    dates: tuple[int, ...]
    shift_types: tuple[int, ...]
    coefficients: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class CompiledExportExtraRow:
    """Resolved selectors for one extra row."""

    people: tuple[int, ...]
    shift_types: tuple[int, ...]


@dataclass(frozen=True)
class CompiledExport:
    """Resolved export selectors aligned with the source export rules."""

    formatting: tuple[CompiledExportFormattingRule, ...]
    extra_columns: tuple[CompiledExportExtraColumn, ...]
    extra_rows: tuple[CompiledExportExtraRow, ...]


@dataclass(frozen=True)
class CompiledSchedule:
    """Validated, index-based schedule data shared by downstream phases."""

    dates: tuple[datetime.date, ...]
    map_sid_s: Mapping[int | str, tuple[int, ...]]
    map_pid_p: Mapping[int | str, tuple[int, ...]]
    map_did_d: Mapping[str, tuple[int, ...]]
    histories: tuple[tuple[int, ...] | None, ...]
    preferences: tuple[CompiledPreference, ...]
    export: CompiledExport

    def __deepcopy__(self, _memo):
        """Reuse this immutable snapshot when Pydantic deep-copies its model."""
        return self


class NurseSchedulingData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    _compiled_schedule: CompiledSchedule = PrivateAttr()

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

        self._compiled_schedule = _validate_and_compile_schedule(self)
        return self

    @property
    def compiled_schedule(self) -> CompiledSchedule:
        """Return the compiled snapshot of the values seen during validation."""
        return self._compiled_schedule


def _build_reference_index(item_ids, groups, reserved, reference_name):
    """Expand ordered item and group IDs into concrete index tuples.

    Item IDs map directly to their indices. The caller seeds reserved
    selectors such as ALL and OFF. Groups can reference items or earlier
    groups, and each group is flattened and deduplicated.
    """
    reference_map = {item_id: (index,) for index, item_id in enumerate(item_ids)}
    reference_map.update(reserved)
    for group in groups:
        expanded = set()
        for member in group.members:
            if member not in reference_map:
                raise ValueError(f"Unknown {reference_name} ID: {member}")
            expanded.update(reference_map[member])
        reference_map[group.id] = tuple(sorted(expanded))
    return reference_map


def _build_date_index(data: NurseSchedulingData):
    """Generate dates and expand every supported date selector.

    Concrete YYYY-MM-DD values map to date indices. Keywords and weekdays are
    added before date groups so groups can reference and flatten them. Date
    groups are deduplicated by ``parse_dates``.
    """
    date_range = data.dates.range
    n_days = (date_range.endDate - date_range.startDate).days + 1
    dates = tuple(date_range.startDate + datetime.timedelta(days=index) for index in range(n_days))
    date_map = {str(date): (index,) for index, date in enumerate(dates)}
    for keyword, predicate in MAP_DATE_KEYWORD_TO_FILTER.items():
        date_map[keyword] = tuple(index for index, date in enumerate(dates) if predicate(date))
    for weekday_index, keyword in enumerate(MAP_WEEKDAY_TO_STR):
        date_map[keyword] = tuple(index for index, date in enumerate(dates) if date.weekday() == weekday_index)
    for group in data.dates.groups:
        date_map[group.id] = tuple(utils.parse_dates(group.members, date_map, date_range))
    return dates, date_map


def _compile_nested_groups(value, parser):
    """Resolve each top-level nested selector into one concrete group.

    Shift affinity treats every top-level people or shift selector as one
    group. Nested selectors combine multiple IDs within that group. The parser
    rejects unknown leaf IDs while preserving these supported shapes.
    """
    groups = []
    for selector in value:
        members = selector if isinstance(selector, list) else [selector]
        groups.append(tuple(parser(members)))
    return tuple(groups)


def _compile_shift_requirement_groups(value, shift_map):
    """Normalize requirement selectors into concrete staffing equations.

    Each inner tuple is one staffing equation. A group selector expands inside
    that equation, while separate top-level selectors create separate
    equations. Examples:

    - ``D`` or ``[D]`` becomes ``[[D]]``.
    - ``ALL``, ``[ALL]``, or ``[[ALL]]`` becomes ``[[D, E, N]]``.
    - ``Group(D, E)`` or ``[Group(D, E)]`` becomes ``[[D, E]]``.
    - ``[D, E]`` becomes ``[[D], [E]]``.
    - ``[[D, E]]`` becomes ``[[D, E]]``.
    """
    selectors = value if isinstance(value, list) else [value]
    return tuple(
        tuple(utils.parse_sids(selector if isinstance(selector, list) else [selector], shift_map))
        for selector in selectors
    )


def _compile_coefficients(entries, selected, shift_map, label, selection_name):
    """Validate and resolve coefficients for a selected shift set."""
    coefficients = dict.fromkeys(selected, 1)
    covered = set()
    for shift_type_id, coefficient in entries or []:
        if coefficient < 1:
            raise ValueError(f"{label} for '{shift_type_id}' must be at least 1.")
        if shift_type_id not in shift_map:
            raise ValueError(f"Unknown shift type ID: {shift_type_id}")
        expanded = set(shift_map[shift_type_id])
        if not expanded.issubset(selected):
            raise ValueError(f"{label} for '{shift_type_id}' must be covered by {selection_name}.")
        if covered.intersection(expanded):
            raise ValueError(f"Duplicate {label.lower()} for '{shift_type_id}'.")
        covered.update(expanded)
        for shift_type in expanded:
            coefficients[shift_type] = coefficient
    return tuple(sorted(coefficients.items()))


def _classify_shift_request_shape(data, dates, person_target, date_target, parsed_dates):
    """Classify a request using its original selector granularity."""
    person_item_ids = {person.id for person in data.people.items}
    people_group_ids = {group.id for group in data.people.groups}
    date_item_ids = {str(date) for date in dates}
    date_group_ids = {group.id for group in data.dates.groups}
    date_keyword_ids = set(MAP_DATE_KEYWORD_TO_FILTER) | set(MAP_WEEKDAY_TO_STR)

    if person_target in person_item_ids:
        person_shape = "person-item"
    elif person_target in people_group_ids:
        person_shape = "people-group"
    else:
        return "unknown"

    date_id = str(date_target)
    if date_id in date_item_ids:
        date_shape = "date-item"
    elif date_id in date_group_ids or date_id in date_keyword_ids:
        date_shape = "date-group"
    else:
        date_shape = "date-item" if len(parsed_dates) == 1 else "date-group"
    return f"{person_shape}-to-{date_shape}"


def _compile_shift_request(data, preference, people_map, shift_map, date_map, dates):
    """Validate and resolve a shift request without losing target shape.

    Frontend edits compact real date items together, while date groups remain
    separate preferences so overlapping groups can stack. Older YAML can still
    mix targets in ``preference.date``. Each original target therefore retains
    its item or group shape before expansion to concrete schedule dates. Export
    formatting uses that original shape when matching request conditions.
    """
    people = tuple(utils.parse_pids(preference.person, people_map))
    shift_types = tuple(utils.parse_sids(preference.shiftType, shift_map))
    person_targets = utils.ensure_list(preference.person)
    date_targets = utils.ensure_list(preference.date)
    shift_type_targets = utils.ensure_list(preference.shiftType)
    compiled_date_targets = []
    for date_target in date_targets:
        parsed_dates = tuple(utils.parse_dates(date_target, date_map, data.dates.range))
        request_shape = "unknown"
        if len(person_targets) == 1 and len(shift_type_targets) == 1:
            request_shape = _classify_shift_request_shape(
                data,
                dates,
                person_targets[0],
                date_target,
                parsed_dates,
            )
        compiled_date_targets.append(CompiledShiftRequestDateTarget(parsed_dates, request_shape))
    resolved_dates = tuple(sorted({date for target in compiled_date_targets for date in target.dates}))
    return CompiledShiftRequest(
        people=people,
        dates=resolved_dates,
        shift_types=shift_types,
        date_targets=tuple(compiled_date_targets),
        requested_shift_type=", ".join(str(target) for target in shift_type_targets),
    )


def _compile_preference(data, preference, people_map, shift_map, date_map, dates):
    """Validate and resolve one preference into solver-ready indices."""
    all_dates = tuple(range(len(dates)))
    if isinstance(preference, MaxOneShiftPerDayPreference):
        return None
    if isinstance(preference, ShiftRequestPreference):
        return _compile_shift_request(data, preference, people_map, shift_map, date_map, dates)
    if isinstance(preference, ShiftTypeSuccessionsPreference):
        people = tuple(utils.parse_pids(preference.person, people_map))
        if not preference.pattern:
            raise ValueError("Pattern must not be empty")
        # Convert each possibly nested pattern element into concrete shift IDs.
        pattern = tuple(
            CompiledPatternElement(
                shift_types=shift_types,
                matches_all_working_shifts=utils.is_ss_equivalent_to_all(shift_types, len(data.shiftTypes.items)),
            )
            for shift_types in _compile_nested_groups(
                preference.pattern,
                lambda members: utils.parse_sids(members, shift_map),
            )
        )
        # An omitted date selector applies the pattern to the full date range.
        selected_dates = (
            tuple(utils.parse_dates(preference.date, date_map, data.dates.range))
            if preference.date is not None
            else all_dates
        )
        return CompiledShiftTypeSuccessions(
            people=people,
            dates=selected_dates,
            date_set=frozenset(selected_dates),
            pattern=pattern,
        )
    if isinstance(preference, ShiftTypeRequirementsPreference):
        shift_groups = _compile_shift_requirement_groups(preference.shiftType, shift_map)
        if not shift_groups or any(not group for group in shift_groups):
            raise ValueError(f"Non-empty shift types are required, but got {preference.shiftType}")
        if any(OFF_sid in group for group in shift_groups):
            raise ValueError(
                "'OFF' is not allowed in shift type requirement preferences. "
                "To specify a zero-shift day, define an ALL shift type for that date "
                "with requiredNumPeople set to 0."
            )
        if preference.shiftTypeCoefficients and len(shift_groups) != 1:
            raise ValueError(
                "Shift type requirement coefficients are only supported when shiftType normalizes to one "
                "requirement group."
            )
        selected_shift_types = set().union(*shift_groups)
        coefficients = _compile_coefficients(
            preference.shiftTypeCoefficients,
            selected_shift_types,
            shift_map,
            "Shift type requirement coefficient",
            "shiftType",
        )
        if preference.preferredNumPeople is not None and preference.weight in {math.inf, -math.inf}:
            raise ValueError(
                f"Infinity weights are not allowed for {SHIFT_TYPE_REQUIREMENT} with 'preferredNumPeople'. "
                "Use 'requiredNumPeople' instead to enforce hard constraints."
            )
        qualified_people = (
            tuple(utils.parse_pids(preference.qualifiedPeople, people_map))
            if preference.qualifiedPeople is not None
            else None
        )
        selected_dates = (
            tuple(utils.parse_dates(preference.date, date_map, data.dates.range))
            if preference.date is not None
            else all_dates
        )
        return CompiledShiftTypeRequirements(
            dates=selected_dates,
            shift_type_groups=shift_groups,
            coefficients=coefficients,
            qualified_people=qualified_people,
        )
    if isinstance(preference, ShiftCountPreference):
        people = tuple(utils.parse_pids(preference.person, people_map))
        selected_dates = tuple(utils.parse_dates(preference.countDates, date_map, data.dates.range))
        shift_types = tuple(utils.parse_sids(preference.countShiftTypes, shift_map))
        if not shift_types:
            raise ValueError(f"Non-empty count shift types are required, but got {preference.countShiftTypes}")
        coefficients = _compile_coefficients(
            preference.countShiftTypeCoefficients,
            set(shift_types),
            shift_map,
            "Shift count coefficient",
            "countShiftTypes",
        )
        expressions = tuple(utils.ensure_list(preference.expression))
        targets = tuple(utils.ensure_list(preference.target))
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
        return CompiledShiftCount(
            people=people,
            dates=selected_dates,
            shift_types=shift_types,
            coefficients=coefficients,
            expressions=expressions,
            targets=targets,
        )
    if isinstance(preference, ShiftAffinityPreference):
        selected_dates = tuple(utils.parse_dates(preference.date, date_map, data.dates.range))
        if not preference.people1 or not preference.people2:
            raise ValueError("Shift affinity people selections must not be empty")
        if not preference.shiftTypes:
            raise ValueError("Shift affinity shift types must not be empty")
        return CompiledShiftAffinity(
            dates=selected_dates,
            # Each people1 element becomes one resolved person group.
            people1_groups=_compile_nested_groups(
                preference.people1,
                lambda members: utils.parse_pids(members, people_map),
            ),
            # Each people2 element becomes one resolved person group.
            people2_groups=_compile_nested_groups(
                preference.people2,
                lambda members: utils.parse_pids(members, people_map),
            ),
            # Each shiftTypes element becomes one resolved shift group.
            shift_type_groups=_compile_nested_groups(
                preference.shiftTypes,
                lambda members: utils.parse_sids(members, shift_map),
            ),
        )
    raise TypeError(f"Unsupported preference model: {type(preference).__name__}")


def _compile_export(data, people_map, shift_map, date_map):
    """Validate and resolve export references against the canonical schedule."""
    formatting = []
    for rule in data.export.formatting:
        people = ()
        dates = ()
        shift_types = ()
        if hasattr(rule, "people"):
            for target in rule.people:
                if target not in people_map:
                    raise ValueError(
                        f"Invalid person identifier '{target}' in export formatting rule with type '{rule.type}'"
                    )
            people = tuple(utils.parse_pids(rule.people, people_map))
        if hasattr(rule, "dates"):
            dates = tuple(utils.parse_dates(rule.dates, date_map, data.dates.range))
        if hasattr(rule, "shiftTypes"):
            for target in rule.shiftTypes:
                if target not in shift_map:
                    raise ValueError(
                        f"Invalid shift type identifier '{target}' in export formatting rule with type 'cell'"
                    )
            shift_types = tuple(utils.parse_sids(rule.shiftTypes, shift_map))
        if isinstance(rule, ExportCellFormattingRule) and rule.when:
            weight_range = rule.when.preference.weightRange
            if weight_range is not None and len(weight_range) != 2:
                raise ValueError("export formatting preference weightRange must contain exactly two values")
            if weight_range is not None and weight_range[0] > weight_range[1]:
                raise ValueError(
                    "export formatting preference weightRange minimum must be less than or equal to maximum"
                )
        formatting.append(CompiledExportFormattingRule(people, dates, shift_types))

    extra_columns = []
    for rule in data.export.extraColumns:
        shift_types = tuple(utils.parse_sids(rule.countShiftTypes, shift_map))
        extra_columns.append(
            CompiledExportExtraColumn(
                dates=tuple(utils.parse_dates(rule.countDates, date_map, data.dates.range)),
                shift_types=shift_types,
                coefficients=_compile_coefficients(
                    rule.countShiftTypeCoefficients,
                    set(shift_types),
                    shift_map,
                    "Export extra column coefficient",
                    "countShiftTypes",
                ),
            )
        )
    extra_rows = tuple(
        CompiledExportExtraRow(
            people=tuple(utils.parse_pids(rule.countPeople, people_map)),
            shift_types=tuple(utils.parse_sids(rule.countShiftTypes, shift_map)),
        )
        for rule in data.export.extraRows
    )
    return CompiledExport(tuple(formatting), tuple(extra_columns), extra_rows)


def _validate_and_compile_schedule(data: NurseSchedulingData) -> CompiledSchedule:
    """Validate canonical semantics and compile reusable index-based data."""
    if data.apiVersion != "alpha":
        raise ValueError(f"Unsupported API version: {data.apiVersion}")

    # Map shift items to indices, add the ALL and OFF reserved selectors, then
    # flatten and deduplicate shift type groups.
    shift_ids = [item.id for item in data.shiftTypes.items]
    shift_map = _build_reference_index(
        shift_ids,
        data.shiftTypes.groups,
        {ALL: tuple(range(len(shift_ids))), OFF: (OFF_sid,)},
        "shift type",
    )
    # Map people to indices, add the ALL selector, then flatten and deduplicate
    # people groups.
    people_ids = [item.id for item in data.people.items]
    people_map = _build_reference_index(
        people_ids,
        data.people.groups,
        {ALL: tuple(range(len(people_ids)))},
        "person",
    )
    dates, date_map = _build_date_index(data)
    histories = tuple(
        None if person.history is None else tuple(shift_map[shift_type_id][0] for shift_type_id in person.history)
        for person in data.people.items
    )
    preferences = tuple(
        _compile_preference(data, preference, people_map, shift_map, date_map, dates) for preference in data.preferences
    )
    compiled_export = _compile_export(data, people_map, shift_map, date_map)
    return CompiledSchedule(
        dates=dates,
        map_sid_s=_FrozenMapping(shift_map),
        map_pid_p=_FrozenMapping(people_map),
        map_did_d=_FrozenMapping(date_map),
        histories=histories,
        preferences=preferences,
        export=compiled_export,
    )
