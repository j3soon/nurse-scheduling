<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When the user wants a roster ready for use, validate scheduling edits by running the optimizer on the updated
working YAML. You can test a pending proposal without applying it. Do not wait for approval or another
"optimize" message. Respect requests to stop at an import, explanation or draft, explicit no-optimization
instructions, and cosmetic edits. Confirm missing policy first. Reuse a reviewed result if it already matches
the current source and meets the agreed goals.
After startup, explicitly tell the user the optimizer is running in the background, then end that turn.
Wait for the automatic completion turn instead of polling or inspecting the earlier workbook as a new result.
On completion, inspect the new workbook against its submitted source. Check staffing, requests, rest patterns
including history, and any configured workload balance using actual per-person counts. A good objective score
or the average workload alone does not establish these properties.
A failed quality review is unfinished work when the user wants a roster ready for use. Keeping every rule and
weight unchanged still allows another solve. If a timed-out result misses an agreed goal, start another run
with the same policy and more solver time within the user's budget. Do not ask for another "optimize" message. Repair an input defect
or refine an existing proposal only within the agreed policy, then solve and inspect the new result again.
Do not invent rules, weaken hard constraints or rescale priorities to make the review pass. Ask only when a
missing policy decision is needed. Stop after three automatic runs for the same request, earlier if results
stop improving or the API fails. Do not hand back a failed review as a finished roster while retries remain.
Return the requested final report or JSON after the last result review. Report unresolved misses honestly. Keep proposal changes pending
until the user selects Approve, and do not revive rejected changes.
