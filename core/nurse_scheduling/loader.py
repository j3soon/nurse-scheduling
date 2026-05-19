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
from ruamel.yaml import YAML
from typing import Dict, Any
from .models import NurseSchedulingData

yaml = YAML(typ='safe')


class InputError(ValueError):
    """Raised when user-provided input fails validation (HTTP 400 candidate)."""
    pass

def _load_yaml(content: bytes) -> Dict[str, Any]:
    """Load YAML from bytes content.
    
    Args:
        content: File content as bytes
    
    Returns:
        Dict[str, Any]: The loaded YAML data
    """
    stream = BytesIO(content)
    # Use ruamel.yaml instead of PyYAML to support YAML 1.2
    # This avoids the auto-conversion of special strings such as
    # `Off` into boolean value `False`.
    return yaml.load(stream)

def load_data(content: bytes) -> NurseSchedulingData:
    """Load nurse scheduling data from YAML bytes content.
    
    Args:
        content: File content as bytes
    
    Returns:
        NurseSchedulingData: The validated scheduling data
    """
    try:
        data = _load_yaml(content)
    except Exception as e:
        raise InputError(f"Invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise InputError(
            "Invalid YAML input: expected a mapping (key-value object) at the top level, "
            f"but got {type(data).__name__}."
        )
    try:
        return NurseSchedulingData(**data)
    except TypeError as e:
        # e.g. unexpected/missing keyword arguments from a malformed mapping
        raise InputError(f"Invalid scheduling data: {e}") from e
