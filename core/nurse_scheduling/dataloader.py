import os
from datetime import date
from typing import Any, Dict, List

from pydantic import Field, model_validator, ConfigDict
from pydantic.dataclasses import dataclass
from typing_extensions import Annotated, Self

from ruamel.yaml import YAML

yaml = YAML(typ='safe')

# Base models
@dataclass(kw_only=True)
class Person:
    model_config = ConfigDict(strict=True)
    id: int | str
    description: str | None = None

@dataclass(kw_only=True)
class PeopleGroup:
    model_config = ConfigDict(strict=True)
    id: int | str
    description: str | None = None
    people: List[int | str]  # Can reference person IDs or other group IDs

@dataclass(kw_only=True)
class Requirement:
    model_config = ConfigDict(strict=True)
    id: int | str
    description: str | None = None
    required_people: int

@dataclass(kw_only=True)
class BasePreference:
    model_config = ConfigDict(strict=True)
    type: str

@dataclass(kw_only=True)
class ShiftRequestPreference(BasePreference):
    model_config = ConfigDict(strict=True)
    type: Annotated[str, Field(pattern="^shift request$")] = "shift request"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    date: (int | str | date) | List[int | str | date]  # Single date or list of dates
    shift: str  # Can reference single requirement ID
    weight: int = Field(default=1)

@dataclass(kw_only=True)
class UnwantedPatternPreference(BasePreference):
    model_config = ConfigDict(strict=True)
    type: Annotated[str, Field(pattern="^unwanted shift type successions$")] = "unwanted shift type successions"
    person: (int | str) | List[int | str]  # Single person/group ID or list
    pattern: List[str]  # List of requirement IDs
    weight: int = Field(default=-1)

@dataclass(kw_only=True)
class EvenShiftDistributionPreference(BasePreference):
    model_config = ConfigDict(strict=True)
    type: Annotated[str, Field(pattern="^assign shifts evenly$")] = "assign shifts evenly"
    weight: int = Field(default=-1)

@dataclass(kw_only=True)
class GeneralPreference(BasePreference):
    model_config = ConfigDict(strict=True)
    type: Annotated[str, Field(
        pattern="^(all requirements fulfilled|all people work at most one shift per day)$"
    )]

@dataclass(kw_only=True)
class NurseSchedulingData:
    model_config = ConfigDict(strict=True)
    apiVersion: str
    description: str | None = None
    startdate: date
    enddate: date
    people: List[Person]
    requirements: List[Requirement]
    preferences: List[GeneralPreference | ShiftRequestPreference | UnwantedPatternPreference | EvenShiftDistributionPreference]
    people_groups: List[PeopleGroup] = Field(default_factory=list)

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
        requirement_ids = set()
        for req in self.requirements:
            if req.id in requirement_ids:
                raise ValueError(f"Duplicated requirement ID: {req.id}")
            requirement_ids.add(req.id)

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

def _load_yaml(filepath: str) -> Dict[str, Any]:
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File {filepath} should exist")
    with open(filepath, "r") as r:
        # Use ruamel.yaml instead of PyYAML to support YAML 1.2
        # This avoids the auto-conversion of special strings such as
        # `Off` into boolean value `False`.
        return yaml.load(r)

def load_data(filepath: str) -> NurseSchedulingData:
    """Load nurse scheduling data from a YAML file.
    
    Args:
        filepath: Path to the YAML file
    
    Returns:
        NurseSchedulingData: The validated scheduling data
    """
    data = _load_yaml(filepath)
    return NurseSchedulingData(**data)
