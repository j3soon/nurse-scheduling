<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When using Python to read or write schedule data, use `ruamel.yaml` with `YAML(typ="safe")`.
The app uses YAML 1.2. PyYAML uses YAML 1.1, which can change string selectors into booleans
and emit strings as numbers. Do not emit YAML aliases.
