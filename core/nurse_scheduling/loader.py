"""Input loading and schema validation helpers."""

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

from io import BytesIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.events import (
    AliasEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

from .models import NurseSchedulingData

MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 200_000


def _validate_yaml_complexity(content: bytes) -> None:
    """Reject YAML structures that can expand into excessive work."""
    depth = 0
    nodes = 0
    stream = BytesIO(content)

    for event in YAML(typ="safe").parse(stream):
        if isinstance(event, AliasEvent):
            raise ValueError("YAML aliases are not allowed")  # noqa: TRY004
        if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
            depth += 1
            nodes += 1
            if depth > MAX_YAML_DEPTH:
                raise ValueError(f"YAML nesting exceeds the limit of {MAX_YAML_DEPTH}")
        elif isinstance(event, (MappingEndEvent, SequenceEndEvent)):
            depth -= 1
        elif isinstance(event, ScalarEvent):
            nodes += 1

        if nodes > MAX_YAML_NODES:
            raise ValueError(f"YAML node count exceeds the limit of {MAX_YAML_NODES}")


def _load_yaml(content: bytes) -> dict[str, Any]:
    """Load YAML from bytes content.

    Args:
        content: File content as bytes

    Returns:
        dict[str, Any]: The loaded YAML data
    """
    _validate_yaml_complexity(content)
    stream = BytesIO(content)
    # Use ruamel.yaml instead of PyYAML to support YAML 1.2
    # This avoids the auto-conversion of special strings such as
    # `Off` into boolean value `False`.
    data = YAML(typ="safe").load(stream)
    if not isinstance(data, dict):
        raise TypeError("Scheduling YAML must contain a top-level mapping")
    return data


def load_data(content: bytes) -> NurseSchedulingData:
    """Load nurse scheduling data from YAML bytes content.

    Args:
        content: File content as bytes

    Returns:
        NurseSchedulingData: The validated scheduling data
    """
    data = _load_yaml(content)
    return NurseSchedulingData.model_validate(data)
