<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

A completed schedule shows assignments. It does not establish the original hard limits, shift eligibility or weights.
When building schedule data from a completed schedule, use its patterns to suggest candidate rules. Explain the supporting observations and ask the user to confirm or correct the rules before building YAML.
Treat the suggestions as unconfirmed. User-confirmed rules override patterns in the example.
If asked only which rules the workbook establishes, leave unstated rules unknown.
