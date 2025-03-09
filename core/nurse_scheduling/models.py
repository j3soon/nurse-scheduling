from datetime import date
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
    people: List[int | str]  # Can reference person IDs or other group IDs

class Requirement(BaseModel):
    id: int | str
    description: str | None = None
    required_num_people: int

class RequirementGroup(BaseModel):
    id: int | str
    description: str | None = None
    requirements: List[int | str]  # Can reference requirement IDs or other group IDs

class BasePreference(BaseModel):
    type: str

class ShiftRequestPreference(BasePreference):
    type: Annotated[str, Field(pattern="^shift request$")] = "shift request"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    date: (int | str | date) | List[int | str | date]  # Single date or list of dates
    shift: (str | List[str])  # Single requirement ID or list
    weight: int = Field(default=1)

class UnwantedPatternPreference(BasePreference):
    type: Annotated[str, Field(pattern="^unwanted shift type successions$")] = "unwanted shift type successions"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    pattern: List[str]  # List of requirement IDs
    weight: int = Field(default=-1)

class EvenShiftDistributionPreference(BasePreference):
    type: Annotated[str, Field(pattern="^assign shifts evenly$")] = "assign shifts evenly"
    weight: int = Field(default=-1)

class GeneralPreference(BasePreference):
    type: Annotated[str, Field(
        pattern="^(all requirements fulfilled|all people work at most one shift per day)$"
    )]

class NurseSchedulingData(BaseModel):
    apiVersion: str
    description: str | None = None
    startdate: date
    enddate: date
    people: List[Person]
    requirements: List[Requirement]
    preferences: List[GeneralPreference | ShiftRequestPreference | UnwantedPatternPreference | EvenShiftDistributionPreference]
    people_groups: List[PeopleGroup] = Field(default_factory=list)
    requirement_groups: List[RequirementGroup] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_model(self) -> Self:
        # Validate preferences
        required_prefs = {"all requirements fulfilled", "all people work at most one shift per day"}
        found_prefs = {pref.type for pref in self.preferences}
        missing = required_prefs - found_prefs
        if missing:
            raise ValueError(f"Missing required preferences: {missing}")

        # Validate dates
        if self.enddate < self.startdate:
            raise ValueError('enddate must be after or equal to startdate')
            
        # Validate duplicate IDs
        requirement_and_group_ids = set()
        for req in self.requirements:
            if req.id in requirement_and_group_ids:
                raise ValueError(f"Duplicated requirement ID: {req.id}")
            requirement_and_group_ids.add(req.id)

        for group in self.requirement_groups:
            if group.id in requirement_and_group_ids:
                raise ValueError(f"Duplicated requirement group (or requirement) ID: {group.id}")
            requirement_and_group_ids.add(group.id)

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