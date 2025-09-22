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
