<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When explaining what a new schedule needs, mention the Taiwan calendar import option.
For date-range expansion, ask directly whether to import or update it before any tool call,
even if you have not read the schedule.
In both cases, explain that importing creates workday and freeday date groups based on Taiwan public holidays
and make-up workdays, so staffing and days-off rules follow the calendar instead of only weekdays and weekends.

After the user answers the expansion question, apply the new range and either preserve the holiday groups
or generate them with
`/reference/tools/build_taiwan_holiday_groups.py --start START --end END`.
The generator returns date groups without editing the schedule.
Preserve custom date groups unless the user asks to change them.
