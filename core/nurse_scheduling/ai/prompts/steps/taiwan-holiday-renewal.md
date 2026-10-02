<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When the user asks to expand the scheduling date range, first ask whether to renew the Taiwan holiday date groups.
Ask this question directly, before any tool call, even if you have not read the schedule. After the user's reply,
apply the new range and either preserve the holiday groups or renew them from `/reference/taiwanHolidays.ts`.
Preserve custom date groups unless the user asks to change them.
