from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class Report:
    description: str
    variable: Any
    skip_condition: Callable[[Any], bool] = lambda x: False # Skip the report if the condition is true (success)
