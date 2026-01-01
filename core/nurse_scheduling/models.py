"""
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.

Copyright (C) 2023-2026 Johnson Sun

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import datetime
import math
import re
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
from typing_extensions import Annotated, Self
from .constants import ALL, OFF, MAP_WEEKDAY_TO_STR, MAP_DATE_KEYWORD_TO_FILTER

AT_MOST_ONE_SHIFT_PER_DAY = 'at most one shift per day'
SHIFT_TYPE_REQUIREMENT = 'shift type requirement'
SHIFT_REQUEST = 'shift request'
SHIFT_TYPE_SUCCESSIONS = 'shift type successions'
SHIFT_COUNT = 'shift count'
SHIFT_AFFINITY = 'shift affinity'

def validate_weight(weight: int | float) -> int | float:
    """Validate that float weights can only be positive or negative infinity."""
    if isinstance(weight, float):
        if weight != math.inf and weight != -math.inf:
            raise ValueError("Float weights can only be positive infinity or negative infinity.")
    return weight

# Base models
class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None
    history: List[str] | None = None

class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startDate: datetime.date
    endDate: datetime.date

class PeopleGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    members: List[int | str]  # Can reference person IDs or other group IDs

class ShiftType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None

class ShiftTypeGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    members: List[int | str]  # Can reference shift type IDs or other group IDs

class DateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    members: List[int | str | datetime.date]  # Can reference date IDs, group IDs, or date objects

class PeopleContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[Person]
    groups: List[PeopleGroup] = Field(default_factory=list)

class ShiftTypesContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[ShiftType]
    groups: List[ShiftTypeGroup] = Field(default_factory=list)

class DateContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    range: DateRange
    items: List[datetime.date] = Field(default_factory=list)  # Automatically generated from range
    groups: List[DateGroup] = Field(default_factory=list)

class BasePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str

class ShiftRequestPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_REQUEST}$")] = SHIFT_REQUEST
    description: str | None = None
    person: (int | str) | List[int | str]  # Single person/group ID or list
    date: (int | str | datetime.date) | List[int | str | datetime.date]  # Single date or list of dates
    shiftType: (str | List[str])  # Single shift type ID or list
    weight: (int | float) = Field(default=1)  # For float can only be .inf or -.inf
    
    @field_validator('weight')
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)

class ShiftTypeSuccessionsPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_TYPE_SUCCESSIONS}$")] = SHIFT_TYPE_SUCCESSIONS
    description: str | None = None
    person: (int | str) | List[int | str]  # Single person/group ID or list
    pattern: List[str | List[str]]  # List of shift type IDs or nested patterns
    date: (int | str | datetime.date) | List[int | str | datetime.date] | None = None  # Single date or list of dates
    weight: (int | float) = Field(default=1)  # For float can only be .inf or -.inf
    
    @field_validator('weight')
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
    shiftType: (str | List[str])  # Single shift type ID or list of shift type IDs
    requiredNumPeople: int
    qualifiedPeople: (int | str) | List[int | str] | None = None   # Single person/group ID or list or None
    preferredNumPeople: int | None = None  # Preferred number of people for each shift type
    date: (int | str | datetime.date) | List[int | str | datetime.date] | None = None  # Single date or list of dates
    weight: (int | float) = Field(default=-1)  # For float can only be .inf or -.inf
    
    @field_validator('weight')
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)

class ShiftCountPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_COUNT}$")] = SHIFT_COUNT
    description: str | None = None
    person: (int | str) | List[int | str]  # Single person/group ID or list
    countDates: (int | str | datetime.date) | List[int | str | datetime.date]  # Single date or list of dates
    countShiftTypes: (str | List[str])  # Single shift type ID or list
    expression: str | List[str]  # Single mathematical expression or list of mathematical expressions
    target: (int | str) | List[int | str]  # Single target value (int or special constant names) or list of target values
    weight: (int | float) = Field(default=-1)  # For float can only be .inf or -.inf
    
    @field_validator('weight')
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)

class ShiftAffinityPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_AFFINITY}$")] = SHIFT_AFFINITY
    description: str | None = None
    date: (int | str | datetime.date) | List[int | str | datetime.date]  # Single date or list of dates
    people1: List[int | str | List[int | str]]  # First person ID list or nested
    people2: List[int | str | List[int | str]]  # Second person ID list or nested
    shiftTypes: List[str | List[str]]  # Shift type ID list or nested
    weight: (int | float) = Field(default=1)  # For float can only be .inf or -.inf
    
    @field_validator('weight')
    @classmethod
    def validate_weight_field(cls, v):
        return validate_weight(v)

class NurseSchedulingData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appVersion: str | None = None
    apiVersion: str
    description: str | None = None
    dates: DateContainer
    country: str | None = None
    people: PeopleContainer
    shiftTypes: ShiftTypesContainer
    preferences: List[
        MaxOneShiftPerDayPreference |
        ShiftRequestPreference |
        ShiftTypeSuccessionsPreference |
        ShiftTypeRequirementsPreference |
        ShiftCountPreference |
        ShiftAffinityPreference
    ]

    @model_validator(mode='after')
    def validate_model(self) -> Self:
        # Validate preferences
        required_prefs = {AT_MOST_ONE_SHIFT_PER_DAY}
        found_prefs = {pref.type for pref in self.preferences}
        missing = required_prefs - found_prefs
        if missing:
            raise ValueError(f"Missing required preferences: {missing}")

        # Validate dates
        if self.dates.range.endDate < self.dates.range.startDate:
            raise ValueError('enddate must be after or equal to startdate')
            
        # Validate duplicate IDs and reserved IDs
        shift_type_reserved_ids = {k.upper() for k in {ALL, OFF}}
        shift_type_and_group_ids = set()
        for shift_type in self.shiftTypes.items:
            if shift_type.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type ID: {shift_type.id}")
            if str(shift_type.id).upper() in shift_type_reserved_ids:
                raise ValueError(f"Shift type ID cannot be one of the reserved values: {shift_type_reserved_ids}")
            shift_type_and_group_ids.add(shift_type.id)
        for group in self.shiftTypes.groups:
            if group.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type group (or shift type) ID: {group.id}")
            if str(group.id).upper() in shift_type_reserved_ids:
                raise ValueError(f"Shift type group ID cannot be one of the reserved values: {shift_type_reserved_ids}")
            shift_type_and_group_ids.add(group.id)

        # Validate duplicate IDs and reserved IDs
        people_reserved_ids = {k.upper() for k in {ALL}}
        person_and_group_ids = set()
        for person in self.people.items:
            if person.id in person_and_group_ids:
                raise ValueError(f"Duplicated person ID: {person.id}")
            if str(person.id).upper() in people_reserved_ids:
                raise ValueError(f"Person ID cannot be one of the reserved values: {people_reserved_ids}")
            person_and_group_ids.add(person.id)
        for group in self.people.groups:
            if group.id in person_and_group_ids:
                raise ValueError(f"Duplicated people group (or person) ID: {group.id}")
            if str(group.id).upper() in people_reserved_ids:
                raise ValueError(f"People group ID cannot be one of the reserved values: {people_reserved_ids}")
            person_and_group_ids.add(group.id)

        # Validate dates
        if self.dates.items:
            raise ValueError("dates.items is not allowed since it is automatically generated from dates.range")
        date_reserved_ids = {k.upper() for k in MAP_WEEKDAY_TO_STR} | {k.upper() for k in MAP_DATE_KEYWORD_TO_FILTER}
        date_group_ids = set()
        for group in self.dates.groups:
            if group.id in date_group_ids:
                raise ValueError(f"Duplicated date group ID: {group.id}")
            if str(group.id).upper() in date_reserved_ids:
                raise ValueError(f"Date group ID cannot be one of the reserved values: {date_reserved_ids}")
            if re.match(r'^\d{1,2}$', group.id) or \
               re.match(r'^(\d{2})-(\d{2})$', group.id) or \
               re.match(r'^(\d{4})-(\d{2})-(\d{2})$', group.id):
                raise ValueError(f"Date group ID must not be in the format of YYYY-MM-DD, MM-DD, or D: {group.id}")
            date_group_ids.add(group.id)

        return self
