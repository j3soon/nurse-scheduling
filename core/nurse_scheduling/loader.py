"""
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.

Copyright (C) 2023-2025 Johnson Sun

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

import os
from ruamel.yaml import YAML
from typing import Dict, Any
from .models import NurseSchedulingData

yaml = YAML(typ='safe')

def _load_yaml(filepath: str) -> Dict[str, Any]:
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File {filepath} should exist")
    with open(filepath, "r", encoding="utf-8") as r:
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
