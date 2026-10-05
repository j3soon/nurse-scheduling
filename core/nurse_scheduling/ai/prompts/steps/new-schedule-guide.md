<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When the user wants to build a schedule from scratch, read `/reference/user-guide/build-a-real-schedule.md`
before recommending its structure or editing it. Adapt the guide to the user's staffing and rest rules.
When staffing distinguishes seniors or other qualifications, explain the guide's separate `D+`, `E+`, and `N+`
qualified slots early. Represent separate staffing pools with separate shift types and appropriate groups.
Preserve the requested totals and qualifications. Do not merge the pools to make a schedule feasible.
If a shift needs only one qualified pool, its existing shift type can represent it without an extra slot.
