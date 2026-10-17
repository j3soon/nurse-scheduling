<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# File and workbook workflows

For file workflows, check actual delivered bytes and a later message in a fresh
workspace. A claimed download path or a successful first-turn read does not prove
delivery or retention. For complete imports, compare the whole parsed source
with the proposal. Keep a partial-update control.
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

For repeated missing-library errors in an offline sandbox, consider preinstalling
the library instead of adding more instructions to use another one. Check the
rebuilt image with synthetic input. Mark comparisons that relied on its absence
as historical and recheck the affected guidance before changing it.

For read-only attachment questions, check whether inspecting the current
schedule helps answer the user's request. Test a focused attachment question
alongside an explicit comparison request before changing source-selection guidance.
