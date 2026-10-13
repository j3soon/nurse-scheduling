<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

For a People History CSV with one `person,shift,repetition` row per person, compute the final consecutive run from the source cells in code. Count the shift on the day before the schedule starts, including OFF, using calendar dates rather than worksheet column order. Use an integer repetition count.

For full `people.items.history` arrays, preserve all supplied days in chronological order. Do not reduce them to the final run.
