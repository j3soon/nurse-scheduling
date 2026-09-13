# Frontend-editable schedule.yaml

## Shift requests

This focused reference is authoritative for reading, adding, copying, updating, or removing shift requests.

Selector fidelity:
- The document must be one YAML mapping without aliases.
- Frontend IDs and references are strings. Quote numeric-looking IDs and full-date selectors in YAML.
- Every reference must resolve to an existing item, supported reserved selector, or available group.
- Preserve exact selectors. Concrete IDs and group IDs are distinct. `N` and `Night` are different.
- Keep reserved selectors such as `ALL` literal. Do not expand groups or reserved selectors.
- A day-of-month selector such as the 1st is the quoted string `01` unless the user supplied a full date.

Path: preferences.shift request

Fields:
- write `type`: shift request
- required `person`: flat list containing exactly one person or people-group ID
- required `date`: flat list of date or date-group IDs
- required `shiftType`: flat list containing exactly one shift-type ID
- optional `weight`: integer or `.inf` or `-.inf`, default 1
- optional `description`: string

Rules:
- If a request to add a shift request omits the required shift type, ask "Which shift type?" immediately without
  reading this reference or the schedule first.
- A positive weight encourages the assignment and a negative weight discourages it.
- Do not add both `.inf` and `-.inf` requests for the same person, date, and shift type. They require and forbid the
  same assignment. Ask the user which request should remain and make no change until they resolve the conflict.
- For ordinary wants or prefers language without a strength, omit `weight` to use the soft default 1.
- Use the user's exact weight. `.inf` requires the assignment and `-.inf` forbids it.
- Confirm the supplied selectors and matching requests in one focused search.
- A copy preserves the selected source request's date, shift type, weight, and explicit description while replacing
  only the person selector, unless the user requests other changes.
- Updating or removing one request must preserve near-duplicate requests that were not selected.

Minimal frontend-compatible YAML:

```yaml
preferences:
  - type: shift request
    person: [P1]
    date: ['01']
    shiftType: [N]
    weight: 1
```

Related paths:
- preferences
- people
- dates
- shiftTypes
