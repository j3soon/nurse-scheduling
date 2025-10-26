from io import BytesIO
from ruamel.yaml import YAML
from typing import Dict, Any
from .models import NurseSchedulingData

yaml = YAML(typ='safe')

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
    data = _load_yaml(content)
    return NurseSchedulingData(**data)
