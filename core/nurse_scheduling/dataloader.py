import os
from typing import Any, Dict

from munch import DefaultMunch
from ruamel.yaml import YAML

yaml = YAML(typ='safe')

def _load_yaml(filepath: str) -> Dict[str, Any]:
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File {filepath} should exist")
    with open(filepath, "r") as r:
        # Use ruamel.yaml instead of PyYAML to support YAML 1.2
        # Ref: https://github.com/yaml/pyyaml/issues/116
        # This avoids the auto-conversion of special strings such as
        # `Off` into boolean value `False`.
        # Ref: https://stackoverflow.com/q/36463531
        return yaml.load(r)

def load_data(filepath: str, validate: bool = True) -> Dict[str, Any]:
    data = DefaultMunch.fromDict(_load_yaml(filepath))
    if not validate:
        return data
    raise NotImplementedError("Validation is not implemented yet")
