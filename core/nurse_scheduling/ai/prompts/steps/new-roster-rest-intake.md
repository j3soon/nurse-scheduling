<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

Before constructing or optimizing a new Schedule Spec, ask which shift transitions to forbid and the maximum
consecutive working days. Include qualified shift variants in the same rest policy.
Before applying rest rules, confirm how related shift types map to categories. For example, if Night to Day
is forbidden, ask whether administrative shifts count as Day for rest rules and whether Night to administrative
is therefore forbidden. A category question asked only for a same-category streak preference leaves the rest rules
unresolved. Different shift IDs and a list of forbidden transitions do not establish category membership.
Ask direct questions about missing rules. Do not propose workplace defaults or wait for a bad roster.
Use answers already in the conversation. Respect declined rules and requests limited to an import,
staffing draft or explanation.
