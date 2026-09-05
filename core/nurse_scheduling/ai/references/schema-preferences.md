# Frontend-editable schedule.yaml

## Preferences

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

Path: preferences

Scheduling rules and weighted preferences.

Rules:
- Every schedule must include `at most one shift per day`.
- Always write the exact `type` discriminator for every preference.
- References use flat string lists in the frontend-editable shape.
- Finite weights are integers. `.inf` and `-.inf` express hard preferences.
- Two preference types count different things. `shift type requirement` counts how many people a shift type needs on a date. `shift count` counts how many shifts one person works across dates.

Related paths:
- preferences.at most one shift per day
- preferences.shift request
- preferences.shift type successions
- preferences.shift type requirement
- preferences.shift count
- preferences.shift affinity

---

Path: preferences.at most one shift per day

Required rule preventing multiple shifts for one person on one date.

Fields:
- write `type`: at most one shift per day
- optional `description`: string

Minimal frontend-compatible YAML:

preferences:
  - type: at most one shift per day

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- preferences

---

Path: preferences.shift request

Request one shift type for one person over one or more dates.

Fields:
- write `type`: shift request
- required `person`: flat list containing exactly one person or people-group ID
- required `date`: flat list of date or date-group IDs
- required `shiftType`: flat list containing exactly one shift-type ID
- optional `weight`: integer or infinity, default 1
- optional `description`: string

Rules:
- A positive `weight` encourages the requested assignment and a negative weight discourages it.
- A person, date, and shift type supplied by the user map directly to `person`, `date`, and `shiftType`. Confirm those selectors and any matching existing request in one focused search.
- For ordinary language such as wants or prefers without a specified strength, omit `weight` to use the soft default 1. Do not infer a stronger weight from unrelated requests.
- Use the user's exact weight when provided. `.inf` requires the assignment and `-.inf` forbids it.

Minimal frontend-compatible YAML:

preferences:
  - type: shift request
    person: [P1]
    date: [FIRST]
    shiftType: [D]
    weight: 1

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- preferences
- people
- dates
- shiftTypes

---

Path: preferences.shift type successions

Reward or penalize a sequence of shift types for selected people and dates.

Fields:
- write `type`: shift type successions
- required `person`: flat list of person or people-group IDs
- required `pattern`: non-empty flat list of shift-type or shift-type-group IDs or OFF
- required `date`: flat list of date or date-group IDs
- optional `weight`: integer or infinity, default 1
- optional `description`: string

Rules:
- A positive `weight` encourages the complete sequence and a negative weight discourages it.
- `.inf` requires the sequence and `-.inf` forbids it at each selected starting date.
- Preserve every shift token in the requested sequence. For example, E followed by D is [E, D], not [Evening, Day].

Minimal frontend-compatible YAML:

preferences:
  - type: shift type successions
    person: [P1]
    pattern: [D, N]
    date: [FIRST]
    weight: -1

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- preferences
- people
- dates
- shiftTypes

---

Path: preferences.shift type requirement

Require staffing for one shift type or one shift-type group. This is the number of people a shift type needs on a date, so it is the type for how many people work a shift.

Fields:
- write `type`: shift type requirement
- required `shiftType`: flat list of shift-type or shift-type-group IDs
- required `requiredNumPeople`: integer
- required `qualifiedPeople`: flat list of person or people-group IDs
- required `date`: flat list of date or date-group IDs
- optional `shiftTypeCoefficients`: [shift-type ID, positive integer] pairs
- optional `preferredNumPeople`: integer
- optional `weight`: integer or infinity, default -1
- optional `description`: string

Rules:
- Separate entries in `shiftType` create separate staffing requirements.
- Use one shift-type group in `shiftType` when coefficients cover multiple member shift types.
- Coefficient entries are [shift-type or group ID, positive integer] pairs. They must be unique and covered by the single selected requirement entry.
- OFF is not allowed in this preference type.
- Only people selected by `qualifiedPeople` may cover the requirement's shift types on its dates.
- A requested shift type, staffing count, qualified people selector, and date selector map directly to `shiftType`, `requiredNumPeople`, `qualifiedPeople`, and `date`. Confirm those selectors and any existing requirement in one focused search. Do not inspect unrelated shift requests or expand group members to infer eligibility.
- Without `preferredNumPeople`, `requiredNumPeople` is an exact hard staffing count. With `preferredNumPeople`, it becomes the hard minimum and the preferred value is the upper target.
- A preference with `preferredNumPeople` requires a finite `weight`. Infinity weights are rejected. Use a negative weight to encourage reaching the preferred count, and use one preference rather than separate required and preferred entries.
- Without `preferredNumPeople`, `weight` has no effect because the staffing count is an exact constraint.
- Use `date: [ALL]` for every date. Do not express this as a `shift count` preference, which counts one person's shifts instead of the people on a shift.

Minimal frontend-compatible YAML:

preferences:
  - type: shift type requirement
    shiftType: [WORK]
    shiftTypeCoefficients: [[D, 1], [N, 2]]
    requiredNumPeople: 2
    qualifiedPeople: [PEOPLE]
    date: [FIRST]
    weight: -1

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- preferences
- people.groups
- dates.groups
- shiftTypes.groups

---

Path: preferences.shift count

Constrain or score total shift counts for selected people. This counts the shifts one person works across the selected dates, not the people needed on a shift.

Fields:
- write `type`: shift count
- required `person`: flat list of person or people-group IDs
- required `countDates`: flat list of date or date-group IDs. Use ALL for the entire schedule range
- required `countShiftTypes`: flat list of shift-type or group IDs, ALL, or OFF
- required scalar `expression`: one of x = T, x >= T, x <= T, x > T, x < T, |x - T|^2
- required scalar `target`: integer
- optional `countShiftTypeCoefficients`: [shift-type or group ID, positive integer] pairs, for example [[D, 1], [N, 2]]
- optional `weight`: integer or infinity, default -1
- optional `description`: string

Rules:
- `countShiftTypes` must resolve to at least one shift type.
- `x = T` means exactly the target count. The inequality expressions set minimum or maximum counts.
- `target` must be non-negative.
- Use `weight: -.inf` for a hard exact or inequality constraint.
- For `|x - T|^2`, `weight` must be non-positive or `-.inf`. Positive and `.inf` weights are rejected.
- For how many people a shift type needs on a date, use `shift type requirement` instead. A staffing level is not a per-person shift total.
- Coefficients are a list of unique 2-item lists, not a mapping or a list of strings. Each selected shift type may be covered once.

Minimal frontend-compatible YAML:

preferences:
  - type: shift count
    person: [P1]
    countDates: [ALL]
    countShiftTypes: [N]
    expression: x = T
    target: 4
    weight: -.inf

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- preferences
- people
- dates
- shiftTypes

---

Path: preferences.shift affinity

Attract or repel two sets of people on selected dates and shift types.

Fields:
- write `type`: shift affinity
- required `date`: flat list of date or date-group IDs
- required `people1`: flat list of person or people-group IDs
- required `people2`: flat list of person or people-group IDs
- required `shiftTypes`: flat list of shift-type or shift-type-group IDs
- optional `weight`: integer or infinity, default 1
- optional `description`: string

Rules:
- `people1`, `people2`, and `shiftTypes` must each be non-empty.
- A positive `weight` rewards both selections matching on a date. A negative `weight` penalizes that joint match. It does not require the two people to have identical schedules.
- When the user says people should work together without specifying strength, omit `weight` to use the soft default 1. Do not infer a stronger weight from unrelated preferences.
- Use `.inf` or `-.inf` only when the user explicitly asks to require or forbid the affinity match.

Minimal frontend-compatible YAML:

preferences:
  - type: shift affinity
    date: [FIRST]
    people1: [P1]
    people2: [P2]
    shiftTypes: [D]
    weight: 1

This example is validated and authoritative for this shape. Do not search schedule.yaml for another schema example. Read only enough schedule text to preserve values and locate the edit anchor. If the user requested a change and you have that anchor, make the edit next.

Related paths:
- preferences
- people
- dates
- shiftTypes
