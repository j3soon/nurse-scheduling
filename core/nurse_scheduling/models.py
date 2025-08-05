import datetime
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing_extensions import Annotated, Self
from .constants import ALL, OFF

AT_MOST_ONE_SHIFT_PER_DAY = 'at most one shift per day'
SHIFT_TYPE_REQUIREMENT = 'shift type requirement'
SHIFT_REQUEST = 'shift request'
SHIFT_TYPE_SUCCESSIONS = 'shift type successions'
SHIFT_COUNT = 'shift count'

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
    id: int | str
    description: str | None = None
    members: List[int | str]  # Can reference person IDs or other group IDs

class ShiftType(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None

class ShiftTypeGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None
    members: List[int | str]  # Can reference shift type IDs or other group IDs

class PeopleContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[Person]
    groups: List[PeopleGroup] = Field(default_factory=list)

class ShiftTypesContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[ShiftType]
    groups: List[ShiftTypeGroup] = Field(default_factory=list)

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
    weight: (int | str) = Field(default=1)

class ShiftTypeSuccessionsPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_TYPE_SUCCESSIONS}$")] = SHIFT_TYPE_SUCCESSIONS
    description: str | None = None
    person: (int | str) | List[int | str]  # Single person/group ID or list
    pattern: List[str | List[str]]  # List of shift type IDs or nested patterns
    weight: (int | str) = Field(default=1)

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
    weight: (int | str) = Field(default=-1)

class ShiftCountPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern=f"^{SHIFT_COUNT}$")] = SHIFT_COUNT
    description: str | None = None
    person: (int | str) | List[int | str]  # Single person/group ID or list
    countDates: (int | str | datetime.date) | List[int | str | datetime.date]  # Single date or list of dates
    countShiftTypes: (str | List[str])  # Single shift type ID or list
    expression: str | List[str]  # Single mathematical expression or list of mathematical expressions
    target: (int | str) | List[int | str]  # Single target value (int or special constant names) or list of target values
    weight: (int | str) = Field(default=-1)

class NurseSchedulingData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    apiVersion: str
    description: str | None = None
    dateRange: DateRange
    country: str | None = None
    people: PeopleContainer
    shiftTypes: ShiftTypesContainer
    preferences: List[
        MaxOneShiftPerDayPreference |
        ShiftRequestPreference |
        ShiftTypeSuccessionsPreference |
        ShiftTypeRequirementsPreference |
        ShiftCountPreference
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
        if self.dateRange.endDate < self.dateRange.startDate:
            raise ValueError('enddate must be after or equal to startdate')
            
        # Validate duplicate IDs and reserved IDs
        reserved_ids = {ALL, OFF}
        shift_type_and_group_ids = set()
        person_and_group_ids = set()
        
        for shift_type in self.shiftTypes.items:
            if shift_type.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type ID: {shift_type.id}")
            if str(shift_type.id).upper() in reserved_ids:
                raise ValueError(f"Shift type ID cannot be one of the reserved values: {reserved_ids}")
            shift_type_and_group_ids.add(shift_type.id)

        for group in self.shiftTypes.groups:
            if group.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type group (or shift type) ID: {group.id}")
            if str(group.id).upper() in reserved_ids:
                raise ValueError(f"Shift type group ID cannot be one of the reserved values: {reserved_ids}")
            shift_type_and_group_ids.add(group.id)

        for person in self.people.items:
            if person.id in person_and_group_ids:
                raise ValueError(f"Duplicated person ID: {person.id}")
            if str(person.id).upper() in reserved_ids:
                raise ValueError(f"Person ID cannot be one of the reserved values: {reserved_ids}")
            person_and_group_ids.add(person.id)

        for group in self.people.groups:
            if group.id in person_and_group_ids:
                raise ValueError(f"Duplicated people group (or person) ID: {group.id}")
            person_and_group_ids.add(group.id)

        return self
