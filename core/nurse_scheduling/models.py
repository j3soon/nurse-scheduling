import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing_extensions import Annotated, Self

# Base models
class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    description: str | None = None
    history: List[str] | None = None

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

class BasePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str

class ShiftRequestPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern="^shift request$")] = "shift request"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    date: (int | str | datetime.date) | List[int | str | datetime.date]  # Single date or list of dates
    shift_type: (str | List[str])  # Single shift type ID or list
    weight: int = Field(default=1)

class UnwantedPatternPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern="^unwanted shift type successions$")] = "unwanted shift type successions"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    pattern: List[str | List[str]]  # List of shift type IDs or nested patterns
    weight: int = Field(default=-1)

class EvenShiftDistributionPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern="^assign shifts evenly$")] = "assign shifts evenly"
    weight: int = Field(default=-1)

class MaxOneShiftPerDayPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern="^all people work at most one shift per day$")] = "all people work at most one shift per day"

class ShiftTypeRequirementsPreference(BasePreference):
    model_config = ConfigDict(extra="forbid")
    type: Annotated[str, Field(pattern="^shift type requirement$")] = "shift type requirement"
    shift_type: (str | List[str])  # Single shift type ID or list of shift type IDs
    required_num_people: int
    qualified_people: (int | str) | List[int | str] | None = None   # Single person/group ID or list or None
    preferred_num_people: int | None = None  # Preferred number of people for each shift type
    date: (int | str | datetime.date) | List[int | str | datetime.date] | None = None  # Single date or list of dates
    weight: int = Field(default=-1)

class NurseSchedulingData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    apiVersion: str
    description: str | None = None
    startdate: datetime.date
    enddate: datetime.date
    country: str | None = None
    people: List[Person]
    shift_types: List[ShiftType]
    preferences: List[MaxOneShiftPerDayPreference | ShiftRequestPreference | UnwantedPatternPreference | EvenShiftDistributionPreference | ShiftTypeRequirementsPreference]
    people_groups: List[PeopleGroup] = Field(default_factory=list)
    shift_type_groups: List[ShiftTypeGroup] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_model(self) -> Self:
        # Validate preferences
        required_prefs = {"all people work at most one shift per day"}
        found_prefs = {pref.type for pref in self.preferences}
        missing = required_prefs - found_prefs
        if missing:
            raise ValueError(f"Missing required preferences: {missing}")

        # Validate dates
        if self.enddate < self.startdate:
            raise ValueError('enddate must be after or equal to startdate')
            
        # Validate duplicate IDs and reserved IDs
        reserved_ids = {"ALL"}
        shift_type_and_group_ids = set()
        person_and_group_ids = set()
        
        for shift_type in self.shift_types:
            if shift_type.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type ID: {shift_type.id}")
            if str(shift_type.id).upper() in reserved_ids:
                raise ValueError(f"Shift type ID cannot be one of the reserved values: {reserved_ids}")
            shift_type_and_group_ids.add(shift_type.id)

        for group in self.shift_type_groups:
            if group.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type group (or shift type) ID: {group.id}")
            if str(group.id).upper() in reserved_ids:
                raise ValueError(f"Shift type group ID cannot be one of the reserved values: {reserved_ids}")
            shift_type_and_group_ids.add(group.id)

        for person in self.people:
            if person.id in person_and_group_ids:
                raise ValueError(f"Duplicated person ID: {person.id}")
            if str(person.id).upper() in reserved_ids:
                raise ValueError(f"Person ID cannot be one of the reserved values: {reserved_ids}")
            person_and_group_ids.add(person.id)

        for group in self.people_groups:
            if group.id in person_and_group_ids:
                raise ValueError(f"Duplicated people group (or person) ID: {group.id}")
            person_and_group_ids.add(group.id)

        return self
