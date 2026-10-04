<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

To count shift requests or find which people and dates they apply to, run
`python /reference/tools/inspect_shift_requests.py`. Requests with weight 0 are excluded.
Filter by `--weight`, `--person`, or `--date`. Each option can be repeated.
The script returns counts by default. Add `--max-requests N` to show up to N matching request entries.
Each request entry counts its person/date pairs separately. If two entries cover the same
person and date, that pair is counted twice. These counts do not tell you whether all requests
can be satisfied together. The script checks that its saved data matches the current YAML.
If it reports missing or outdated schedule data, read the current YAML instead.
