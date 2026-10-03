<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

For counts or resolved selectors of nonzero shift requests in the current YAML, run
`python /reference/tools/inspect_shift_requests.py`. Filter with repeatable `--weight`, `--person`,
or `--date` options. Counts are returned by default. Add `--max-requests N` for bounded details.
The helper checks the current source
and reports targets per preference entry, not unique cells or joint feasibility. If the context is
unavailable or stale, inspect the current YAML instead.
