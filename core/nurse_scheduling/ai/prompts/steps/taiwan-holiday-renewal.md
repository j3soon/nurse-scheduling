<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When the user asks to expand the scheduling date range, first ask whether to import or update the Taiwan holiday calendar.
Explain that it imports official public holidays and make-up working days into date groups. These groups let staffing
and days-off rules follow workdays and days off instead of only weekdays and weekends. Use plain language rather than
asking only whether to "renew date groups".
Ask this question directly, before any tool call, even if you have not read the schedule. After the user's reply,
apply the new range and either preserve the holiday groups or generate them with
`/reference/tools/build_taiwan_holiday_groups.py --start START --end END`.
The generator returns date groups without editing the schedule.
Preserve custom date groups unless the user asks to change them.
