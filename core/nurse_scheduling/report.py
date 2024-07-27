from dataclasses import dataclass

@dataclass
class Report:
    description: str
    variable: 'typing.Any'
    skip_condition: 'typing.Any' = lambda x: False
