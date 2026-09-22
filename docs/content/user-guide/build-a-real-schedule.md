# Build a Real Schedule

This guide rebuilds the bundled, anonymized 87-person ward schedule for
November 2025 entirely through the running web UI. It is validated
end-to-end: after the steps below, **Save and Load → Download** produces a YAML
file that matches the bundled example
(`large-ward-with-87-people-2025-11.yaml`), except for the `appVersion` stamp,
the top-level `description`, and two group-date requests that the UI stores as
single-date pairs (see [Validate the result](#validate-the-result)).

People are anonymized as `P1` through `P87`. Group descriptions keep the
original ward's mix of English and Chinese labels.

## Data files

The companion files in the `build-a-real-schedule/` directory make
the large, repetitive parts of the schedule importable in one action instead of
hundreds of cell edits:

- [`starter.yaml`](build-a-real-schedule/starter.yaml): a minimal starter with the
  November 2025 date range, the 11 shift types and 5 shift-type groups, and the
  default *at most one shift per day* preference.
- [`people.txt`](build-a-real-schedule/people.txt): the 87 person IDs.
- [`people-history.csv`](build-a-real-schedule/people-history.csv): previous-shift
  history for every person.
- [`shift-requests-strong.csv`](build-a-real-schedule/shift-requests-strong.csv):
  concrete person-date requests at weight `11000000000` (408 cells).
- [`shift-requests-moderate.csv`](build-a-real-schedule/shift-requests-moderate.csv):
  concrete person-date requests at weight `11000000` (90 cells).
- [`reference.yaml`](build-a-real-schedule/reference.yaml): the exact values for the
  groups and rules that the app does not bulk-import. Create these in the UI, in
  the listed order, so the normalized YAML matches the bundled example.

## 1. Load the starter

1. On the app home page, select **New Schedule**, then **Reset Data**, and
   confirm.
2. Open **Save and Load** and select **Upload**.
3. Choose `starter.yaml`.

Because the starter omits `appVersion`, the app shows a version notice such as
*“The loaded file does not contain app version information … Do you want to
continue loading the file?”* Select **OK**. The starter sets the date range,
shift types, shift-type groups, and the default one-shift-per-day preference.

![Starter YAML loaded with the November range and shift types](../assets/images/user-guide/build-a-real-schedule/build-real-starter.png)

## 2. Add the 87 people

1. Open **People** and select **Upload People**.
2. Choose `people.txt`.

The upload adds all 87 people (`P1`–`P87`). Each appears under the automatic
`ALL` group.

![Roster of P1 through P87 under the automatic ALL group](../assets/images/user-guide/build-a-real-schedule/build-real-people.png)

## 3. Add previous-shift history

1. Open **Shift Requests** and select **Quick Add Preference**.
2. Select **Upload People History (shorthand)** and choose `people-history.csv`.

Each row is `person,shift,repetition`. The history fills the `H-1`–`H-6`
columns so succession rules can reach back before November 1.

![Previous-shift history for the ward roster](../assets/images/user-guide/build-a-real-schedule/build-real-history.png)

## 4. Create the date groups

The starter already defines the November 1–30 date range. Create the five ward
date groups listed under `dateGroups` in `reference.yaml`:

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

![Five ward date groups above the automatic calendar groups](../assets/images/user-guide/build-a-real-schedule/build-real-date-groups.png)

## 5. Create the people groups

Create the 13 ward people groups listed under `peopleGroups` in
`reference.yaml`, in that order: `Day People w/o A`, `Day People`,
`Evening People`, `Night People`, `Prev Day People w/o A`, `Prev Evening
People`, `Prev Night People`, `All Nurses w/o Students`, `Senior Nurses`,
`Head Nurses`, `Super Junior Nurses`, `Admin People`, and `Students`.

Open **People**, select **Add Group**, enter the ID and description, and select
the member people from `reference.yaml`. Groups may overlap; the automatic
`ALL` group always holds everyone.

![Thirteen ward people groups with their member chips](../assets/images/user-guide/build-a-real-schedule/build-real-people-groups.png)

## 6. Import the concrete requests

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

## 7. Add the group and person requests

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

![Group rows filled with requests across the date-group columns](../assets/images/user-guide/build-a-real-schedule/build-real-requests.png)

## 8. Add the staffing requirements

Create the 8 shift-type requirements listed under `requirements` in
`reference.yaml`. Open **Shift Type Requirements** and select **Add
Requirement** for each:

- Required and, where present, preferred counts, for example *`N` requires 12,
  prefers 13, qualified `All Nurses w/o Students`, dates `ALL`, weight
  `-1000000000000`*.
- Leave the weight at `-1` for the senior and admin minimums.

![Eight staffing requirements for the ward](../assets/images/user-guide/build-a-real-schedule/build-real-requirements.png)

## 9. Add the succession rules

Create the 14 shift-type successions listed under `successions` in
`reference.yaml`. Open **Shift Type Successions** and add each pattern for
people `ALL` on dates `ALL`. These forbid sequences such as *Day then Night*
(weight `-inf`), limit consecutive shifts, and discourage *Night → Day*
(weight `-1000000000`).

![Fourteen succession rules applied to everyone](../assets/images/user-guide/build-a-real-schedule/build-real-successions.png)

## 10. Add the workload counts

Create the 3 shift counts listed under `shiftCounts` in `reference.yaml`. Open
**Shift Counts** and add each, counting `OFF` with the expression `|x - T|^2`
at weight `-1000`:

- `All Nurses w/o Students` on `ALL`, target `11`.
- `Day People` and `Evening People` on `FREEDAY`, target `4`.
- `Night People` on `FREEDAY`, target `4`.

![Three workload-balancing count rules](../assets/images/user-guide/build-a-real-schedule/build-real-counts.png)

## Validate the result

1. Open **Save and Load** and select **Download**.
2. Compare the downloaded YAML to the bundled example. The `apiVersion`,
   `dates`, `people`, and `shiftTypes` sections match, and every preference
   matches once you group requests by person, shift type, and weight.

The download differs from the bundled example only in three ways, all expected:

- `appVersion` is stamped with the running app version.
- The top-level `description` is whatever the starter set.
- Two group-date requests (*Day People → Evening* and *Evening People → Day*,
  each on `Before 4` and `After 4`) are stored as two single-date requests
  instead of one multi-date request. The app merges concrete date items
  automatically but not date-group items, so the UI represents each as a
  pair. The scheduling effect is identical.

![Downloaded YAML for the completed schedule](../assets/images/user-guide/build-a-real-schedule/build-real-final-yaml.png)

## Next steps

- Refine individual cells or rules, then run
  [Optimize and Export](optimize-and-export.md).
- For a recurring ward, keep `reference.yaml` as the source of truth and
  re-import the CSVs after a roster change, editing only the rules that the
  ward changed.
