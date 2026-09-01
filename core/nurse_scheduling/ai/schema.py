"""Bounded, model-readable guidance for the frontend schedule YAML schema."""

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

# This code is mostly AI generated.

from dataclasses import dataclass
from difflib import get_close_matches

MAX_SCHEMA_RESULT_CHARS = 6_000
SELECTOR_GUIDANCE = (
    "Selector fidelity:\n"
    "- Preserve an exact selector supplied by the user when validation accepts it. IDs such as `Person 3` and "
    "`P3` are different.\n"
    "- Keep reserved selectors such as `ALL` literal. Do not expand a group or reserved selector into its members.\n"
    "- Keep concrete IDs distinct from group IDs. For example, shift type `D` is not group `Day`.\n"
    "- Keep date selectors in the requested form. For example, `01`, `2025-11-01`, and a date-group ID are distinct.\n"
    "- Quote a YAML string containing `: `, `#`, or another syntax-significant character."
)


@dataclass(frozen=True)
class ScheduleSchemaTopic:
    """One focused schema explanation and an optional validated example."""

    summary: str
    fields: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    example: str | None = None
    related: tuple[str, ...] = ()


SCHEMA_TOPICS: dict[str, ScheduleSchemaTopic] = {
    "dates": ScheduleSchemaTopic(
        "Date range and reusable date groups.",
        fields=("required `range`", "optional `groups`, default []"),
        rules=("Do not write `items`. Calendar dates are generated from `range`.",),
        related=("dates.range", "dates.groups"),
    ),
    "dates.range": ScheduleSchemaTopic(
        "Inclusive calendar range for the schedule.",
        fields=("required `startDate`: YYYY-MM-DD", "required `endDate`: YYYY-MM-DD"),
        rules=(
            "`endDate` must be on or after `startDate`.",
            (
                "When shrinking the range, remove every now-out-of-range date from groups and preferences in the "
                "same coordinated file edit. Find their current short or full date selectors with `rg` and "
                "bounded context."
            ),
        ),
        example="""dates:
  range:
    startDate: 2026-01-01
    endDate: 2026-01-31""",
        related=("dates", "dates.groups"),
    ),
    "dates.groups": ScheduleSchemaTopic(
        "Named selectors that contain dates or other date-group IDs.",
        fields=(
            "required `id`: string",
            "required `description`: string, which may be empty",
            "required `members`: flat list of string references",
        ),
        rules=("Date members must fall inside `dates.range`.",),
        example="""dates:
  groups:
    - id: FIRST
      description: ''
      members: ['2026-01-01', '2026-01-02']""",
        related=("dates", "dates.range"),
    ),
    "people": ScheduleSchemaTopic(
        "People and reusable people groups.",
        fields=("required `items`", "optional `groups`, default []"),
        rules=("Frontend IDs and references must be strings.",),
        related=("people.items", "people.groups"),
    ),
    "people.items": ScheduleSchemaTopic(
        "People available for scheduling.",
        fields=(
            "required `id`: string",
            "required `description`: string, which may be empty",
            "optional `history`: flat list of shift-type IDs or OFF",
        ),
        rules=(
            (
                "To remove a person entirely, remove their item, every group membership, and every preference that "
                "names only that person in the same coordinated file edit. Locate every exact reference with "
                "`rg --word-regexp` and bounded context."
            ),
        ),
        example="""people:
  items:
    - id: P1
      description: ''
      history: [D]
    - id: P2
      description: ''
      history: []""",
        related=("people", "people.groups", "shiftTypes.items"),
    ),
    "people.groups": ScheduleSchemaTopic(
        "Named selectors that contain people or other people-group IDs.",
        fields=(
            "required `id`: string",
            "required `description`: string, which may be empty",
            "required `members`: flat list of string references",
        ),
        example="""people:
  groups:
    - id: ALL_NURSES
      description: ''
      members: [P1, P2]""",
        related=("people", "people.items"),
    ),
    "shiftTypes": ScheduleSchemaTopic(
        "Shift types and reusable shift-type groups.",
        fields=("required `items`", "optional `groups`, default []"),
        rules=("Frontend IDs and references must be strings.",),
        related=("shiftTypes.items", "shiftTypes.groups"),
    ),
    "shiftTypes.items": ScheduleSchemaTopic(
        "Individual shift types.",
        fields=("required `id`: string", "required `description`: string, which may be empty"),
        example="""shiftTypes:
  items:
    - id: D
      description: Day
    - id: N
      description: Night""",
        related=("shiftTypes", "shiftTypes.groups"),
    ),
    "shiftTypes.groups": ScheduleSchemaTopic(
        "Named selectors that contain shift types or other shift-type-group IDs.",
        fields=(
            "required `id`: string",
            "required `description`: string, which may be empty",
            "required `members`: flat list of string references",
        ),
        example="""shiftTypes:
  groups:
    - id: WORK
      description: ''
      members: [D, N]""",
        related=("shiftTypes", "shiftTypes.items"),
    ),
    "preferences": ScheduleSchemaTopic(
        "Scheduling rules and weighted preferences.",
        rules=(
            "Every schedule must include `at most one shift per day`.",
            "References use flat string lists in the frontend-editable shape.",
            "Finite weights are integers. `.inf` and `-.inf` express hard preferences.",
            (
                "Two preference types count different things. `shift type requirement` counts how many people a "
                "shift type needs on a date. `shift count` counts how many shifts one person works across dates."
            ),
        ),
        related=(
            "preferences.at most one shift per day",
            "preferences.shift request",
            "preferences.shift type successions",
            "preferences.shift type requirement",
            "preferences.shift count",
            "preferences.shift affinity",
        ),
    ),
    "preferences.at most one shift per day": ScheduleSchemaTopic(
        "Required rule preventing multiple shifts for one person on one date.",
        fields=("required `type`: at most one shift per day", "optional `description`"),
        example="""preferences:
  - type: at most one shift per day""",
        related=("preferences",),
    ),
    "preferences.shift request": ScheduleSchemaTopic(
        "Request one shift type for one person over one or more dates.",
        fields=(
            "required `type`: shift request",
            "required `person`: flat list containing exactly one person or people-group ID",
            "required `date`: flat list of date or date-group IDs",
            "required `shiftType`: flat list containing exactly one shift-type ID",
            "optional `weight`, default 1",
            "optional `description`",
        ),
        example="""preferences:
  - type: shift request
    person: [P1]
    date: [FIRST]
    shiftType: [D]
    weight: 1""",
        related=("preferences", "people", "dates", "shiftTypes"),
    ),
    "preferences.shift type successions": ScheduleSchemaTopic(
        "Reward or penalize a sequence of shift types for selected people and dates.",
        fields=(
            "required `type`: shift type successions",
            "required `person`: flat list of person or people-group IDs",
            "required `pattern`: flat list of shift-type IDs or OFF",
            "required `date`: flat list of date or date-group IDs",
            "optional `weight`, default 1",
            "optional `description`",
        ),
        rules=(
            (
                "Preserve every shift token in the requested sequence. For example, E followed by D is [E, D], not "
                "[Evening, Day]."
            ),
        ),
        example="""preferences:
  - type: shift type successions
    person: [P1]
    pattern: [D, N]
    date: [FIRST]
    weight: -1""",
        related=("preferences", "people", "dates", "shiftTypes"),
    ),
    "preferences.shift type requirement": ScheduleSchemaTopic(
        "Require staffing for one shift type or one shift-type group. This is the number of people a shift type "
        "needs on a date, so it is the type for how many people work a shift.",
        fields=(
            "required `type`: shift type requirement",
            "required `shiftType`: flat list of shift-type or shift-type-group IDs",
            "required `requiredNumPeople`: integer",
            "required `qualifiedPeople`: flat list of person or people-group IDs",
            "required `date`: flat list of date or date-group IDs",
            "optional `shiftTypeCoefficients`: [shift-type ID, positive integer] pairs",
            "optional `preferredNumPeople`, `weight`, and `description`",
        ),
        rules=(
            "Use one shift-type group in `shiftType` when coefficients cover multiple member shift types.",
            "OFF is not allowed in this preference type.",
            (
                "`requiredNumPeople` is the staffing that must be met. Add `preferredNumPeople` with a finite "
                "`weight` to score a better level above it, in one preference rather than two."
            ),
            (
                "Use `date: [ALL]` for every date. Do not express this as a `shift count` preference, which counts "
                "one person's shifts instead of the people on a shift."
            ),
        ),
        example="""preferences:
  - type: shift type requirement
    shiftType: [WORK]
    shiftTypeCoefficients: [[D, 1], [N, 2]]
    requiredNumPeople: 2
    qualifiedPeople: [PEOPLE]
    date: [FIRST]
    weight: -1""",
        related=("preferences", "people.groups", "dates.groups", "shiftTypes.groups"),
    ),
    "preferences.shift count": ScheduleSchemaTopic(
        "Constrain or score total shift counts for selected people. This counts the shifts one person works across "
        "the selected dates, not the people needed on a shift.",
        fields=(
            "required `type`: shift count",
            "required `person`: flat list of person or people-group IDs",
            "required `countDates`: flat list of date or date-group IDs. Use ALL for the entire schedule range",
            "required `countShiftTypes`: flat list of shift-type or group IDs, ALL, or OFF",
            "required scalar `expression`: one of x = T, x >= T, x <= T, x > T, x < T, |x - T|^2",
            "required scalar `target`: integer",
            "optional `countShiftTypeCoefficients`: [shift-type ID, integer] pairs, for example [[D, 1], [N, 2]]",
            "optional `weight` and `description`",
        ),
        rules=(
            "`x = T` means exactly the target count. The inequality expressions set minimum or maximum counts.",
            "Use `weight: -.inf` for a hard exact or inequality constraint.",
            (
                "For how many people a shift type needs on a date, use `shift type requirement` instead. A staffing "
                "level is not a per-person shift total."
            ),
            "Coefficients are a list of 2-item lists, not a mapping or a list of strings.",
        ),
        example="""preferences:
  - type: shift count
    person: [P1]
    countDates: [ALL]
    countShiftTypes: [N]
    expression: x = T
    target: 4
    weight: -.inf""",
        related=("preferences", "people", "dates", "shiftTypes"),
    ),
    "preferences.shift affinity": ScheduleSchemaTopic(
        "Attract or repel two sets of people on selected dates and shift types.",
        fields=(
            "required `type`: shift affinity",
            "required `date`: flat list of date or date-group IDs",
            "required `people1`: flat list of person or people-group IDs",
            "required `people2`: flat list of person or people-group IDs",
            "required `shiftTypes`: flat list of shift-type or shift-type-group IDs",
            "optional `weight`, default 1",
            "optional `description`",
        ),
        example="""preferences:
  - type: shift affinity
    date: [FIRST]
    people1: [P1]
    people2: [P2]
    shiftTypes: [D]
    weight: 1""",
        related=("preferences", "people", "dates", "shiftTypes"),
    ),
    "export": ScheduleSchemaTopic(
        "Spreadsheet formatting and count-based extra rows or columns.",
        fields=(
            "optional `formatting`, default []",
            "optional `extraColumns`, default []",
            "optional `extraRows`, default []",
        ),
        rules=(
            "If `export` is absent, add it as an optional top-level mapping. Its lists may be omitted when unused.",
        ),
        related=("export.formatting", "export.extraColumns", "export.extraRows"),
    ),
    "export.formatting": ScheduleSchemaTopic(
        "Formatting rules selected by their `type`.",
        rules=(
            "Colors use six-digit #RRGGBB strings.",
            "Cell annotations and `when` conditions are supported only by type `cell`.",
        ),
        related=(
            "export.formatting.row",
            "export.formatting.people header",
            "export.formatting.history",
            "export.formatting.column",
            "export.formatting.date header",
            "export.formatting.history header",
            "export.formatting.cell",
        ),
    ),
    "export.formatting.row": ScheduleSchemaTopic(
        "Format spreadsheet rows for selected people.",
        fields=("required `type`: row", "required `people`: flat list of person or group IDs", "optional colors"),
        example="""export:
  formatting:
    - type: row
      people: [P1]
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting",),
    ),
    "export.formatting.people header": ScheduleSchemaTopic(
        "Format people header cells for selected people.",
        fields=(
            "required `type`: people header",
            "required `people`: flat list of person or group IDs",
            "optional colors",
        ),
        example="""export:
  formatting:
    - type: people header
      people: [P1]
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting",),
    ),
    "export.formatting.history": ScheduleSchemaTopic(
        "Format history cells for selected people.",
        fields=(
            "required `type`: history",
            "required `people`: flat list of person or group IDs",
            "optional colors",
        ),
        example="""export:
  formatting:
    - type: history
      people: [P1]
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting",),
    ),
    "export.formatting.column": ScheduleSchemaTopic(
        "Format spreadsheet columns for selected dates.",
        fields=("required `type`: column", "required `dates`: flat list of date or group IDs", "optional colors"),
        example="""export:
  formatting:
    - type: column
      dates: [FIRST]
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting",),
    ),
    "export.formatting.date header": ScheduleSchemaTopic(
        "Format date header cells for selected dates.",
        fields=(
            "required `type`: date header",
            "required `dates`: flat list of date or group IDs",
            "optional colors",
        ),
        example="""export:
  formatting:
    - type: date header
      dates: [FIRST]
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting",),
    ),
    "export.formatting.history header": ScheduleSchemaTopic(
        "Format the shared history header.",
        fields=("required `type`: history header", "optional colors"),
        rules=(
            "If `export` is absent, add this `export` mapping at the top level. Other export lists may be omitted.",
        ),
        example="""export:
  formatting:
    - type: history header
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting", "export.formatting.history"),
    ),
    "export.formatting.cell": ScheduleSchemaTopic(
        "Format schedule cells selected by people, dates, and shift types.",
        fields=(
            "required `type`: cell",
            "required `people`, `dates`, and `shiftTypes`: flat string-reference lists",
            "optional colors, `appendText`, `note: {text: ...}`, and `when`",
        ),
        rules=(
            "`when.preference.types` currently supports only [shift request].",
            "A preference condition may filter by `requestShape`, `satisfied`, or two-value `weightRange`.",
        ),
        example="""export:
  formatting:
    - type: cell
      people: [P1]
      dates: [FIRST]
      shiftTypes: [D]
      backgroundColor: '#e0f2fe'""",
        related=("export.formatting", "preferences.shift request"),
    ),
    "export.extraColumns": ScheduleSchemaTopic(
        "Add per-person columns that count selected shifts over selected dates.",
        fields=(
            "required `type`: count",
            "required `header`: string",
            "required `countShiftTypes`: flat list of shift-type or group IDs",
            "required `countDates`: flat list of date or group IDs. Use ALL for the entire schedule range",
            "optional `countShiftTypeCoefficients`, `description`, and `rightBorderColor`",
        ),
        rules=(
            "If `export` is absent, add this `export` mapping at the top level. Other export lists may be omitted.",
        ),
        example="""export:
  extraColumns:
    - type: count
      header: Nights
      countShiftTypes: [N]
      countDates: [ALL]""",
        related=("export", "export.extraRows"),
    ),
    "export.extraRows": ScheduleSchemaTopic(
        "Add per-date rows that count selected shifts over selected people.",
        fields=(
            "required `type`: count",
            "required `header`: string",
            "required `countShiftTypes`: flat list of shift-type or group IDs",
            "required `countPeople`: flat list of person or group IDs. Use ALL to count every person",
            "optional `description` and `bottomBorderColor`",
        ),
        example="""export:
  extraRows:
    - type: count
      header: Night staffing
      countShiftTypes: [N]
      countPeople: [ALL]""",
        related=("export", "export.extraColumns"),
    ),
}

SCHEMA_PATHS = tuple(SCHEMA_TOPICS)


def render_schedule_schema(path: str | None = None) -> str | None:
    """Render the root index or one known schema topic."""
    if path is None:
        paths = "\n".join(f"- {value}" for value in SCHEMA_PATHS)
        return (
            "Frontend-editable schedule.yaml schema\n\n"
            "Required top-level fields:\n"
            "- apiVersion: alpha\n"
            "- dates\n"
            "- people\n"
            "- shiftTypes\n"
            "- preferences\n\n"
            "Optional top-level fields:\n"
            "- appVersion\n"
            "- description\n"
            "- export\n\n"
            "Choose the most specific path. A leaf example is validated and sufficient to construct that shape.\n\n"
            f"{SELECTOR_GUIDANCE}\n\n"
            f"Available paths:\n{paths}"
        )

    topic = SCHEMA_TOPICS.get(path)
    if topic is None:
        return None
    sections = [f"Path: {path}", topic.summary, SELECTOR_GUIDANCE]
    if topic.fields:
        sections.append("Fields:\n" + "\n".join(f"- {field}" for field in topic.fields))
    if topic.rules:
        sections.append("Rules:\n" + "\n".join(f"- {rule}" for rule in topic.rules))
    if topic.example:
        sections.append(f"Minimal frontend-compatible YAML:\n\n{topic.example}")
        sections.append(
            "This example is validated and authoritative for this shape. Do not search schedule.yaml for another "
            "schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the "
            "user requested a change and you have that anchor, make the edit next."
        )
    if topic.related:
        sections.append("Related paths:\n" + "\n".join(f"- {related}" for related in topic.related))
    rendered = "\n\n".join(sections)
    return rendered[:MAX_SCHEMA_RESULT_CHARS]


def closest_schema_paths(path: str) -> tuple[str, ...]:
    """Suggest known paths for a non-conforming provider call."""
    return tuple(get_close_matches(path, SCHEMA_PATHS, n=3, cutoff=0.25))
