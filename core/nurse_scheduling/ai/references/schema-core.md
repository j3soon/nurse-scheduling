# Frontend-editable schedule.yaml

## Core structure: dates, people, and shift types

---

This document intentionally groups related shapes. Read it once when working in this domain instead of searching for each field separately.

---

Selector fidelity:
- The document must be one YAML mapping without aliases.
- Unknown mapping fields are rejected. Use only fields documented for that shape.
- Frontend IDs and references are strings. Quote numeric-looking IDs and full-date selectors in YAML.
- Every reference must resolve to an existing item, supported reserved selector, or available group.
- Preserve an exact selector supplied by the user when validation accepts it. IDs such as `Person 3` and `P3` are different.
- Keep reserved selectors such as `ALL` literal. Do not expand a group or reserved selector into its members.
- Keep concrete IDs distinct from group IDs. For example, shift type `D` is not group `Day`.
- Keep date selectors in the requested form. For example, `01`, `2025-11-01`, and a date-group ID are distinct.
- Quote a YAML string containing `: `, `#`, or another syntax-significant character.

---

Path: schedule

Top-level frontend-editable schedule document.

Fields:
- required `apiVersion`: alpha
- required `dates`
- required `people`
- required `shiftTypes`
- required `preferences`
- optional `appVersion`: string
- optional `description`: string
- optional `export`: mapping, default empty

Related paths:
- dates
- people
- shiftTypes
- preferences
- export

---

Path: dates

Date range and reusable date groups.

Fields:
- required `range`: mapping
- optional empty `items`: list, default []
- optional `groups`: list, default []

Rules:
- Calendar dates are generated from `range`. Do not add entries to `items`. Preserve an existing empty `items` field unless the user asks to remove it.

Related paths:
- dates.range
- dates.groups

---

Path: dates.range

Inclusive calendar range for the schedule.

Fields:
- required `startDate`: YYYY-MM-DD
- required `endDate`: YYYY-MM-DD

Rules:
- `endDate` must be on or after `startDate`.
- When shrinking the range, remove every now-out-of-range date in one coordinated file edit. Date selectors can occur in `dates.groups[].members`, preference `date` or `countDates`, export formatting `dates`, and export extra-column `countDates`. Search once with `rg` for all equivalent short, MM-DD, full-date, and range forms of the removed dates. Do not repeat that search by section or inspect unrelated preferences. Read containing blocks only where an entry may need deletion, then make the remaining replacements together. If an explicit preference or export rule loses its entire date scope, delete that entry instead of leaving an empty selector or omitting the selector, which could broaden its meaning.

Minimal frontend-compatible YAML:

dates:
  range:
    startDate: 2026-01-01
    endDate: 2026-01-31

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- dates
- dates.selectors
- dates.groups

---

Path: dates.selectors

Supported string selectors for one date or a set of dates.

Fields:
- concrete date: D within a single-month schedule, MM-DD within a single-year schedule, or YYYY-MM-DD
- inclusive range: START~END using compatible concrete-date formats
- reserved set: ALL, WEEKDAY, WEEKEND, or MONDAY through SUNDAY
- named date-group ID

Rules:
- Every resolved concrete date must fall inside `dates.range`.

Related paths:
- dates.range
- dates.groups

---

Path: dates.groups

Named selectors that contain dates or other date-group IDs.

Fields:
- required `id`: string
- required `description`: string, which may be empty
- required `members`: flat list of string references

Rules:
- Date members must resolve inside `dates.range`.
- Members may name concrete dates, inclusive date ranges, date keywords, weekdays, or groups defined earlier in the list.
- Group IDs must be unique. They cannot be reserved date keywords or weekdays, and cannot look like day-of-month, MM-DD, or YYYY-MM-DD dates. Reserved-name checks are case-insensitive.

Minimal frontend-compatible YAML:

dates:
  groups:
    - id: FIRST
      description: ''
      members: ['2026-01-01', '2026-01-02']

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- dates
- dates.range
- dates.selectors

---

Path: people

People and reusable people groups.

Fields:
- required `items`: list
- optional `groups`: list, default []

Rules:
- Frontend IDs and references must be strings.

Related paths:
- people.items
- people.groups

---

Path: people.items

People available for scheduling.

Fields:
- required `id`: string
- required `description`: string, which may be empty
- optional `history`: flat list of shift-type IDs or OFF

Rules:
- Person IDs must be unique and cannot case-insensitively equal the reserved selector ALL.
- History may contain concrete shift-type IDs or OFF, but not ALL or shift-type group IDs.
- To remove a person entirely, remove their item, every group membership, and every preference that names only that person in the same coordinated file edit. Locate every exact reference with `rg --word-regexp` and bounded context.

Minimal frontend-compatible YAML:

people:
  items:
    - id: P1
      description: ''
      history: [D]
    - id: P2
      description: ''
      history: []

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- people
- people.groups
- shiftTypes.items

---

Path: people.groups

Named selectors that contain people or other people-group IDs.

Fields:
- required `id`: string
- required `description`: string, which may be empty
- required `members`: flat list of string references

Rules:
- Group IDs must be unique across people and groups and cannot case-insensitively equal the reserved selector ALL.
- Members may name people or groups defined earlier in the list.

Minimal frontend-compatible YAML:

people:
  groups:
    - id: ALL_NURSES
      description: ''
      members: [P1, P2]

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- people
- people.items

---

Path: shiftTypes

Shift types and reusable shift-type groups.

Fields:
- required `items`: list
- optional `groups`: list, default []

Rules:
- Frontend IDs and references must be strings.

Related paths:
- shiftTypes.items
- shiftTypes.groups

---

Path: shiftTypes.items

Individual shift types.

Fields:
- required `id`: string
- required `description`: string, which may be empty

Rules:
- Shift-type IDs must be unique and cannot case-insensitively equal the reserved selectors ALL or OFF.

Minimal frontend-compatible YAML:

shiftTypes:
  items:
    - id: D
      description: Day
    - id: N
      description: Night

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- shiftTypes
- shiftTypes.groups

---

Path: shiftTypes.groups

Named selectors that contain shift types or other shift-type-group IDs.

Fields:
- required `id`: string
- required `description`: string, which may be empty
- required `members`: flat list of string references

Rules:
- Group IDs must be unique across shift types and groups and cannot case-insensitively equal the reserved selectors ALL or OFF.
- Members may name shift types or groups defined earlier in the list.

Minimal frontend-compatible YAML:

shiftTypes:
  groups:
    - id: WORK
      description: ''
      members: [D, N]

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- shiftTypes
- shiftTypes.items
