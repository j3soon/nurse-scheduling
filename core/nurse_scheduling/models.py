import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Annotated, Self

# Base models
class Person(BaseModel):
    id: int | str
    description: str | None = None

class PeopleGroup(BaseModel):
    id: int | str
    description: str | None = None
    members: List[int | str]  # Can reference person IDs or other group IDs

class ShiftType(BaseModel):
    id: int | str
    description: str | None = None

class ShiftTypeGroup(BaseModel):
    id: int | str
    description: str | None = None
    members: List[int | str]  # Can reference shift type IDs or other group IDs

class BasePreference(BaseModel):
    type: str

class ShiftRequestPreference(BasePreference):
    type: Annotated[str, Field(pattern="^shift request$")] = "shift request"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    date: (int | str | datetime.date) | List[int | str | datetime.date]  # Single date or list of dates
    shift_type: (str | List[str])  # Single shift type ID or list
    weight: int = Field(default=1)

class UnwantedPatternPreference(BasePreference):
    type: Annotated[str, Field(pattern="^unwanted shift type successions$")] = "unwanted shift type successions"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    pattern: List[str]  # List of shift type IDs
    weight: int = Field(default=-1)

class EvenShiftDistributionPreference(BasePreference):
    type: Annotated[str, Field(pattern="^assign shifts evenly$")] = "assign shifts evenly"
    weight: int = Field(default=-1)

class MaxOneShiftPerDayPreference(BasePreference):
    type: Annotated[str, Field(pattern="^all people work at most one shift per day$")] = "all people work at most one shift per day"

class ShiftTypeRequirementsPreference(BasePreference):
    type: Annotated[str, Field(pattern="^shift type requirement$")] = "shift type requirement"
    shift_type: (str | List[str])  # Single shift type ID or list of shift type IDs
    required_num_people: int
    qualified_people: List[int | str] | None = None  # List of person IDs who are qualified for these shift types
    preferred_num_people: int | None = None  # Preferred number of people for each shift type
    date: (int | str | datetime.date) | List[int | str | datetime.date] | None = None  # Single date or list of dates
    weight: int = Field(default=-1)

class NurseSchedulingData(BaseModel):
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
            
        # Validate duplicate IDs
        shift_type_and_group_ids = set()
        for shift_type in self.shift_types:
            if shift_type.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type ID: {shift_type.id}")
            shift_type_and_group_ids.add(shift_type.id)

        for group in self.shift_type_groups:
            if group.id in shift_type_and_group_ids:
                raise ValueError(f"Duplicated shift type group (or shift type) ID: {group.id}")
            shift_type_and_group_ids.add(group.id)

        person_and_group_ids = set()
        for person in self.people:
            if person.id in person_and_group_ids:
                raise ValueError(f"Duplicated person ID: {person.id}")
            person_and_group_ids.add(person.id)

        for group in self.people_groups:
            if group.id in person_and_group_ids:
                raise ValueError(f"Duplicated people group (or person) ID: {group.id}")
            person_and_group_ids.add(group.id)
            
        return self 