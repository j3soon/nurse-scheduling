# Frontend-editable schedule.yaml

## Export formatting and count rows or columns

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

Path: export

Spreadsheet formatting and count-based extra rows or columns.

Fields:
- optional `formatting`: list, default []
- optional `extraColumns`: list, default []
- optional `extraRows`: list, default []

Rules:
- If `export` is absent, add it as an optional top-level mapping. Its lists may be omitted when unused.

Related paths:
- export.formatting
- export.extraColumns
- export.extraRows

---

Path: export.formatting

Formatting rules selected by their `type`.

Fields:
- all variants optionally accept `description`: string
- all variants optionally accept `backgroundColor`, `bottomBorderColor`, `rightBorderColor`, and `fontColor`

Rules:
- Colors use six-digit #RRGGBB strings.
- Cell annotations and `when` conditions are supported only by type `cell`.

Related paths:
- export.formatting.row
- export.formatting.people header
- export.formatting.history
- export.formatting.column
- export.formatting.date header
- export.formatting.history header
- export.formatting.cell

---

Path: export.formatting.row

Format spreadsheet rows for selected people.

Fields:
- required `type`: row
- required `people`: flat list of person or group IDs
- optional colors

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: row
      people: [P1]
      backgroundColor: '#e0f2fe'

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting

---

Path: export.formatting.people header

Format people header cells for selected people.

Fields:
- required `type`: people header
- required `people`: flat list of person or group IDs
- optional colors

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: people header
      people: [P1]
      backgroundColor: '#e0f2fe'

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting

---

Path: export.formatting.history

Format history cells for selected people.

Fields:
- required `type`: history
- required `people`: flat list of person or group IDs
- optional colors

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: history
      people: [P1]
      backgroundColor: '#e0f2fe'

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting

---

Path: export.formatting.column

Format spreadsheet columns for selected dates.

Fields:
- required `type`: column
- required `dates`: flat list of date or group IDs
- optional colors

Rules:
- For a day-of-month request such as 'the 1st', use the quoted two-digit selector `01`. Do not replace it with a full date unless the user supplied that full-date selector.

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: column
      dates: ['01']
      fontColor: '#ff0000'

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting

---

Path: export.formatting.date header

Format date header cells for selected dates.

Fields:
- required `type`: date header
- required `dates`: flat list of date or group IDs
- optional colors

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: date header
      dates: [FIRST]
      backgroundColor: '#e0f2fe'

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting

---

Path: export.formatting.history header

Format the shared history header.

Fields:
- required `type`: history header
- optional colors

Rules:
- If `export` is absent, add this `export` mapping at the top level. Other export lists may be omitted.

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: history header
      backgroundColor: '#e0f2fe'

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting
- export.formatting.history

---

Path: export.formatting.cell

Format schedule cells selected by people, dates, and shift types.

Fields:
- required `type`: cell
- required `people`, `dates`, and `shiftTypes`: flat string-reference lists
- optional common formatting fields and `appendText`: string
- optional `note`: mapping with required `text`
- optional `when`: formatting condition mapping

Rules:
- `when.preference.types` currently supports only [shift request].
- `when` has the exact shape `preference: {types: [shift request], requestShape: [...], satisfied: true, weightRange: [MIN, MAX]}`. `requestShape`, `satisfied`, and `weightRange` are independently optional.

Minimal frontend-compatible YAML:

export:
  formatting:
    - type: cell
      people: [ALL]
      dates: [ALL]
      shiftTypes: [ALL]
      backgroundColor: '#00ff00'
      when:
        preference:
          types: [shift request]
          satisfied: true

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export.formatting
- export.formatting.condition
- preferences.shift request

---

Path: export.formatting.condition

Conditionally apply a cell formatting rule based on a matching preference.

Fields:
- required `preference`: preference condition mapping

Rules:
- Conditions are supported only by formatting rules with `type: cell`.

Related paths:
- export.formatting.cell
- export.formatting.condition.preference

---

Path: export.formatting.condition.preference

Select the shift-request preferences that control conditional cell formatting.

Fields:
- required `types`: [shift request]
- optional `requestShape`: flat list containing person-item-to-date-item, people-group-to-date-item, person-item-to-date-group, people-group-to-date-group, or ALL
- optional `satisfied`: boolean
- optional `weightRange`: two-value numeric list

Rules:
- `weightRange` must contain exactly [minimum, maximum], with minimum no greater than maximum.

Related paths:
- export.formatting.cell
- export.formatting.condition

---

Path: export.formatting.note

Attach a note to a cell formatting rule.

Fields:
- required `text`: string

Rules:
- Notes are supported only by formatting rules with `type: cell`.

Related paths:
- export.formatting.cell

---

Path: export.extraColumns

Add per-person columns that count selected shifts over selected dates.

Fields:
- required `type`: count
- required `header`: string
- required `countShiftTypes`: flat list of shift-type or group IDs
- required `countDates`: flat list of date or group IDs. Use ALL for the entire schedule range
- optional `countShiftTypeCoefficients`: [shift-type or group ID, positive integer] pairs covered by `countShiftTypes`
- optional `description`: string and `rightBorderColor`: #RRGGBB string

Rules:
- If `export` is absent, add this `export` mapping at the top level. Other export lists may be omitted.
- Coefficient entries must be unique and may cover each selected shift type once.

Minimal frontend-compatible YAML:

export:
  extraColumns:
    - type: count
      header: Nights
      countShiftTypes: [N]
      countDates: [ALL]

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export
- export.extraRows

---

Path: export.extraRows

Add per-date rows that count selected shifts over selected people.

Fields:
- required `type`: count
- required `header`: string
- required `countShiftTypes`: flat list of shift-type or group IDs
- required `countPeople`: flat list of person or group IDs. Use ALL to count every person
- optional `description`: string and `bottomBorderColor`: #RRGGBB string

Minimal frontend-compatible YAML:

export:
  extraRows:
    - type: count
      header: Night staffing
      countShiftTypes: [N]
      countPeople: [ALL]

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- export
- export.extraColumns
