# Screen and Control Reference

## Screens

| Screen | Use it for | Needed for a basic run |
| --- | --- | --- |
| [Home](../index.md) | Start or reset a schedule and view the app build | Once |
| [Dates](dates.md) | Set the scheduling period and date groups | Yes |
| [People](people.md) | Manage people and reusable groups | Yes |
| [Shift Types](shift-types.md) | Manage working shifts and groups | Yes |
| [Shift Type Requirements](shift-type-requirements.md) | Define staffing by shift, qualification, and date | Yes for a controlled result |
| [Shift Requests](shift-requests.md) | Record preferred and avoided assignments | Optional |
| [Shift Type Successions](shift-type-successions.md) | Encourage or forbid shift sequences | Optional |
| [Shift Counts](shift-counts.md) | Set workload totals or bounds | Optional |
| [Shift Affinities](shift-affinities.md) | Encourage or discourage working together | Optional |
| [Export Layout](export-layout.md) | Format XLSX and add summary rows or columns | Optional |
| [Save and Load](save-and-load.md) | Back up, restore, copy, or inspect YAML | Recommended |
| [Optimize and Export](optimize-and-export.md) | Select a server and download the solved XLSX | Yes |

## Shared controls

- Select the question-mark icon beside a page title to open its guide in a new
  tab without closing an unfinished form.
- Double-click an ID or description to edit it where supported.
- Drag rows to change display and export order.
- Drag across checkbox lists or request cells for repeated selection.
- Use the edit, duplicate, and delete actions on saved rules.
- Save or cancel an open form before changing tabs. Leaving an unfinished form
  discards its edits after confirmation.

## Keyboard shortcuts

Number and arrow navigation shortcuts are ignored while typing in a field.
Undo and redo remain global, so use care when editing text.

| Key | Action |
| --- | --- |
| `0` to `9` | Open the matching numbered tab |
| `Left` or `Right` | Previous or next tab |
| `Up` or `Down` | Scroll by one screen |
| `Ctrl+Z` or `Cmd+Z` | Undo |
| `Ctrl+Y` or `Cmd+Y` | Redo |

Tabs 10 and 11 are reached with the navigation bar or arrow keys.

## Weights

The solver maximizes the total score.

| Rule | Weight effect |
| --- | --- |
| Request, succession, or affinity | Positive encourages. Negative discourages. |
| Preferred staffing | A larger negative value penalizes a larger gap from preferred staffing. |
| Count comparison | Positive encourages the comparison to be true. Negative discourages it. |
| Squared count distance | A larger negative value favors a count closer to the target. |
| Supported infinity control | Makes the selected condition or avoidance hard. |

Do not use infinity for preferred staffing. Other infinity controls depend on
the rule and comparison. Conflicting hard rules make the schedule infeasible.

## Automatic entries

- `ALL` groups include every item of that type and update automatically.
- `OFF` is the automatic no-work shift type.
- Weekday and weekend date groups update from the date range.
- Renaming or deleting people, dates, or shift types updates references in
  preferences and export layout entries.
