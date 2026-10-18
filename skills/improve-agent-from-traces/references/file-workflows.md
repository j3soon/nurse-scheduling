<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# File and workbook workflows

For file workflows, check actual delivered bytes and a later message in a fresh
workspace. A claimed download path or a successful first-turn read does not prove
delivery or retention. For complete imports, compare the whole parsed source
with the proposal. Keep a partial-update control.
Grade construction of YAML schedule data from an XLSX workbook by its validated proposal. Require a specific tool only when
its use establishes evidence that the final artifact cannot show.
For generated import files, grade the delivered file against the destination
importer's row and field rules. Test malformed output with the real importer
to detect silent conversions. Fix parser defects separately from model mistakes.
Pair a summarized format with a full-history control. Keep its instruction
scoped to that format so the agent preserves data in other formats.

For workbook imports, validate an independent correct proposal with both the
frontend validator and the grader before live runs. Check that each format
belongs to the correct cell and that finite weights stay finite. Grade
clarification, construction, solving and delivery separately. A run that fails
clarification does not establish anything about optimizer behavior.
For onboarding from an XLSX completed schedule, test useful rule suggestions
with their observed evidence and a request for confirmation. Do not grade
uncertainty alone as successful onboarding. State any required JSON field types
in the question, so a valid alternative format does not fail the grader.
Observed patterns support candidate rules, but do not establish the original
hard limits, eligibility or weights.
Contrast a fact-only question with a request to infer rules. Test a later user
correction and check that the YAML uses the confirmed rules instead of the
example's patterns. Keep solver-result explanations in a separate prompt step.

For confirmed-analysis reuse, test an unchanged mapping, a corrected mapping and
a follow-up that needs previously unread data. Check the resulting proposal and
second-turn commands separately. A valid import alone does not prove reuse.
Later turns retain assistant answers and may retain the bounded, source-bound
`/workspace/analysis.md` file. Tool results and other scratch files are discarded.
Test source changes, rejected commits and retention limits before relying on
saved analysis. New user corrections override notes. Keep mandatory-rule failures
separate from redundant exploration when assessing a candidate.

For repeated missing-library errors in an offline sandbox, consider preinstalling
the library instead of adding more instructions to use another one. Check the
rebuilt image with synthetic input. Mark comparisons that relied on its absence
as historical and recheck the affected guidance before changing it.

For read-only attachment questions, check whether inspecting the current
schedule helps answer the user's request. Test a focused attachment question
alongside an explicit comparison request before changing source-selection guidance.

For inline attachment scripts, group repeated operations before proposing helpers.
Separate source inspection from schedule construction and domain policy audits.
For workbook value/style frequencies and row/column counts, use
`/reference/tools/inspect_xlsx.py FILE --summary --range 'Sheet!B2:AC61' --styles --axis row`.
The same inspector reads uploaded and generated workbooks. Summary mode reports
blanks, formulas and truncated groups. Omit `--summary` for individual cells. Keep value types distinct
and missing formula caches unknown. Test a changed layout and contrasting formula
case. Grade answers independently of helper use, then inspect generated commands
before claiming that the agent avoided custom scripts.
