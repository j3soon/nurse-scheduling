# Build a Real Schedule

This guide rebuilds the bundled, anonymized 87-person ward schedule for
November 2025 entirely through the running web UI, starting from an empty
schedule. It is validated end-to-end: after the steps below, **Save and Load →
Download** produces a YAML file that matches the bundled example
(`large-ward-with-87-people-2025-11.yaml`), except for the `appVersion` stamp
and two group-date requests that the UI stores as single-date pairs (see
[Validate the result](#validate-the-result)).

People are anonymized as `P1` through `P87`. Group descriptions keep the
original ward's mix of English and Chinese labels.

## How the example is organized

The files preserve one ward's configuration. Use the numbers as an example to
review with your own scheduler, not as staffing targets for another ward.

- **Shift types:** `D`, `E`, and `N` separate day, evening, and night work.
  Their `+` variants have separate senior-nurse requirements. `D~`, `E~`, and
  `N~` keep student shifts distinct from counted nurse staffing.
- **Shift and people groups:** One request or rule can select several shifts or
  people. People can belong to overlapping groups, so review the rules they
  receive together.
- **Ward date groups:** `WORKDAY` and `FREEDAY` select dates for staffing and
  counts. `Freeday shift right` lists weekend dates shifted one calendar day
  later, but no rule in this example currently selects it.
- **November 4 split:** `Before 4` and `After 4` apply different cross-team
  request weights. The configured penalty is stronger from November 4.

Weights express how strongly the optimizer scores a preference: positive
weights encourage it, negative weights discourage it, and `-inf` forbids it.
A large finite penalty is still a preference, not a prohibition. The
[Shift Requests](shift-requests.md),
[Shift Type Requirements](shift-type-requirements.md), and
[Shift Type Successions](shift-type-successions.md) pages explain how each rule
is applied. The source data does not explain the ward's clinical reason for
every number or group boundary.

## Data files

The companion files in the `build-a-real-schedule/` directory make the large,
repetitive parts of the schedule importable in one action instead of hundreds
of cell edits:

- [`people.txt`](build-a-real-schedule/people.txt): the 87 person IDs.
- [`people-history.csv`](build-a-real-schedule/people-history.csv): previous-shift
  history for every person.
- [`shift-requests-strong.csv`](build-a-real-schedule/shift-requests-strong.csv):
  concrete person-date requests at weight `11000000000` (408 cells).
- [`shift-requests-moderate.csv`](build-a-real-schedule/shift-requests-moderate.csv):
  concrete person-date requests at weight `11000000` (90 cells).
- [`reference.yaml`](build-a-real-schedule/reference.yaml): the exact values for the
  shift types, groups, and rules that the app does not bulk-import. Create these
  in the UI, in the listed order, so the normalized YAML matches the bundled
  example.

The November 1–30 date range is entered on the Dates page in step 1; it is not
imported from a file.

## 1. Start from empty and set the dates

1. On the app home page, select **New Schedule**, then **Create empty schedule**,
   and confirm. The new schedule already includes the default *at most one shift
   per day* preference.
2. Open **Dates** and select **Set Date Range**.
3. Set the start date to `2025-11-01` and the end date to `2025-11-30` (30 days
   selected).
4. Leave **Import Taiwan holidays into date groups** unchecked; the ward defines
   its own `WORKDAY` and `FREEDAY` groups in step 5.
5. Select **Update**.

The app creates one date item per day (`01`–`30`) and the automatic groups
`ALL`, `WEEKDAY`, `WEEKEND`, and the weekday names.

![November 1–30 range with the automatic date groups](../assets/images/user-guide/build-a-real-schedule/build-real-dates-range.png)

## 2. Create the shift types

Create the 11 shift types listed under `shiftTypes.items` in `reference.yaml`,
in that order: `D`, `D+`, `E`, `E+`, `N`, `N+`, `A`, `D~`, `E~`, `N~`, and `K`.
Open **Shift Types**, select **Add Shift Type**, enter the ID and description,
and select **Add**. Repeat for each shift type.

The automatic `OFF` shift type and `ALL` group are always present and cannot be
edited or deleted.

The `+` shifts have separate senior-nurse coverage requirements in step 9.
The `~` descriptions say that new staff do not count toward staffing; the
`Student Shifts` group lets the schedule refer to those shifts together.
`K` is labeled as class or training in the reference data.

Then create the 5 shift-type groups listed under `shiftTypes.groups` in
`reference.yaml`, in that order: `Day`, `Day (w/o A, D~, K)`, `Evening`,
`Night`, and `Student Shifts`. Select **Add Group**, enter the ID and
description, select the member shift types, and select **Add**.

![Eleven shift types and five shift-type groups with their members](../assets/images/user-guide/build-a-real-schedule/build-real-shift-types.png)

## 3. Add the 87 people

1. Open **People** and select **Upload People**.
2. Choose `people.txt`.

The upload adds all 87 people (`P1`–`P87`). Each appears under the automatic
`ALL` group.

![Roster of P1 through P87 under the automatic ALL group](../assets/images/user-guide/build-a-real-schedule/build-real-people.png)

## 4. Add previous-shift history

1. Open **Shift Requests** and select **Quick Add Preference**.
2. Select **Upload People History (shorthand)** and choose `people-history.csv`.

Each row is `person,shift,repetition`. The history fills the `H-1`–`H-6`
columns so succession rules can reach back before November 1.

![Previous-shift history for the ward roster](../assets/images/user-guide/build-a-real-schedule/build-real-history.png)

## 5. Create the date groups

The November 1–30 range is already set. Create the five ward date groups listed
under `dateGroups` in `reference.yaml`:

| ID | Members |
| --- | --- |
| `WORKDAY` | 20 workdays |
| `FREEDAY` | 10 freedays |
| `Freeday shift right` | 9 days |
| `Before 4` | `01`, `02`, `03` |
| `After 4` | `04`–`30` |

Open **Dates**, select **Add Group**, enter the ID and description, and select
the member dates (the **List view** checkbox list is easiest for many members).
Keep the creation order from `reference.yaml`.

`FREEDAY` contains the ten weekends in this month. `Freeday shift right`
contains the following dates for nine of them because November 30 falls at
the end of the schedule. It is present in the source schedule but unused by
its rules. Review both date lists and whether the unused group is still needed
when carrying this pattern into another month.

![Five ward date groups above the automatic calendar groups](../assets/images/user-guide/build-a-real-schedule/build-real-date-groups.png)

## 6. Create the people groups

Create the 13 ward people groups listed under `peopleGroups` in
`reference.yaml`, in that order: `Day People w/o A`, `Day People`,
`Evening People`, `Night People`, `Prev Day People w/o A`, `Prev Evening
People`, `Prev Night People`, `All Nurses w/o Students`, `Senior Nurses`,
`Head Nurses`, `Super Junior Nurses`, `Admin People`, and `Students`.

Open **People**, select **Add Group**, enter the ID and description, and select
the member people from `reference.yaml`. Groups may overlap; the automatic
`ALL` group always holds everyone.

The team groups drive cross-team requests, while `Senior Nurses`, `Admin
People`, and `All Nurses w/o Students` select who can satisfy the corresponding
staffing requirements. Group membership is an eligibility and rule-selection
choice, not a label to infer from an anonymized ID.

![Thirteen ward people groups with their member chips](../assets/images/user-guide/build-a-real-schedule/build-real-people-groups.png)

## 7. Import the concrete requests

The two CSVs hold every request for a specific person on a specific date.
Because a CSV upload applies one weight to every non-empty cell, the cells are
split by weight into two uploads.

1. Open **Shift Requests** and select **Quick Add Preference**.
2. Set **Weight** to `11000000000`, select **Upload Shift Requests**, and choose
   `shift-requests-strong.csv` (408 cells).
3. Set **Weight** to `11000000`, then select **Upload Shift Requests** and choose
   `shift-requests-moderate.csv` (90 cells).

Each row is one person; the columns line up with the displayed dates. Blank
cells are ignored, so the two uploads do not conflict.

## 8. Add the group and person requests

Create the 33 shift requests listed under `shiftRequests` in `reference.yaml`
with **Quick Add Preference**. These are the requests the CSVs do not cover:

- 25 group-level requests (24 ward groups plus the `ALL` group), such as *Day
  People → Evening on `Before 4` and `After 4` at weight `-100000000`* and *Day
  People w/o A → `A` on `ALL` at weight `-inf`*.
- 8 person-level requests on `ALL` for `P1`–`P3`, such as *`P1` → `D` and `OFF`
  on `ALL`*.

For each entry, choose the shift type, set the weight (use the `-inf` / `inf`
controls for infinite weights), and click the group-row × date-column cell.
Red cells show discouraged or forbidden work.

The group requests discourage cross-team work with finite negative weights.
Some of those penalties become stronger after November 3. The
`-inf` requests prohibit specific combinations, including
student shifts for `All Nurses w/o Students`. Check the exact weights and date
selectors in `reference.yaml` before adapting these requests.

![Group rows filled with requests across the date-group columns](../assets/images/user-guide/build-a-real-schedule/build-real-requests.png)

## 9. Add the staffing requirements

Create the 8 shift-type requirements listed under `requirements` in
`reference.yaml`. Open **Shift Type Requirements** and select **Add
Requirement** for each:

- Required and, where present, preferred counts, for example *`N` requires 12,
  prefers 13, qualified `All Nurses w/o Students`, dates `ALL`, weight
  `-1000000000000`*.
- Leave the weight at `-1` for the senior and admin minimums.

The `D`, `E`, and `N` requirements count non-student nurses and set a preferred
headcount one above the required minimum. `D` has separate workday and freeday
levels. The `+` requirements count senior nurses, and the freeday `A`
requirement uses `Admin People`. These are the example's configured staffing
levels, not a recommendation for another ward.

![Eight staffing requirements for the ward](../assets/images/user-guide/build-a-real-schedule/build-real-requirements.png)

## 10. Add the succession rules

Create the 14 shift-type successions listed under `successions` in
`reference.yaml`. Open **Shift Type Successions** and add each pattern for
people `ALL` on dates `ALL`. These forbid sequences such as *Day then Night*
(weight `-inf`), limit consecutive shifts, and discourage *Night → Day*
(weight `-1000000000`).

Previous-shift history from step 4 lets a pattern crossing November 1 be
checked. The three two-shift transitions with `-inf` and six consecutive
working shifts are prohibited. Other patterns have finite positive or negative
weights and can trade off against the rest of the schedule.

![Fourteen succession rules applied to everyone](../assets/images/user-guide/build-a-real-schedule/build-real-successions.png)

## 11. Add the workload counts

Create the 3 shift counts listed under `shiftCounts` in `reference.yaml`. Open
**Shift Counts** and add each, counting `OFF` with the expression `|x - T|^2`
at weight `-1000`:

- `All Nurses w/o Students` on `ALL`, target `11`.
- `Day People` and `Evening People` on `FREEDAY`, target `4`.
- `Night People` on `FREEDAY`, target `4`.

Each rule scores every selected person's own count. The squared expression
penalizes a larger gap from the target more strongly, but a target can be
missed when other rules take priority. Review the resulting `OFF` counts per
person rather than treating these targets as guaranteed totals.

![Three workload-balancing count rules](../assets/images/user-guide/build-a-real-schedule/build-real-counts.png)

## Validate the result

1. Open **Save and Load** and select **Download**.
2. Compare the downloaded YAML to the bundled example. The `apiVersion`,
   `description`, `dates`, `people`, and `shiftTypes` sections match, and every
   preference matches once you group requests by person, shift type, and
   weight.

The download differs from the bundled example only in two ways, both expected:

- `appVersion` is stamped with the running app version.
- Two group-date requests (*Day People → Evening* and *Evening People → Day*,
  each on `Before 4` and `After 4`) are stored as two single-date requests
  instead of one multi-date request. The app merges concrete date items
  automatically but not date-group items, so the UI represents each as a
  pair. The scheduling effect is identical.

![Downloaded YAML for the completed schedule](../assets/images/user-guide/build-a-real-schedule/build-real-final-yaml.png)

## Next steps

Before optimizing, have the scheduler review the roster and group memberships,
the dates in `WORKDAY` and `FREEDAY`, previous-shift history, staffing levels,
and every `-inf` rule. Also confirm which finite preferences may be traded off
when the schedule is crowded. Resolve unintended warnings on the staffing
requirements page.

Then refine individual requests or rules and run
[Optimize and Export](optimize-and-export.md). Review the resulting assignments,
coverage, and `OFF` counts with the scheduler before using the schedule. For a
recurring ward, update the dates, roster, history, and imports for the new
period, then review every group and rule again.
