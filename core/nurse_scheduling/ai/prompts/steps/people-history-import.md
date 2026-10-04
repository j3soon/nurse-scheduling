<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When preparing a People History (shorthand) CSV, generate `person,shift,repetition` rows from the source cells in code. Use the shift on the day before the schedule starts, including OFF, and count its consecutive occurrences ending on that day. The repetition count is an integer. Read calendar dates to identify that run regardless of worksheet column order.
