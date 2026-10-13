<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When building a new schedule from a workbook, inspect both cell values and formatting. Ask the user to explain any unclear codes, colors or roster sections and supply any missing staffing or rest rules before proposing YAML. Once these are clear, use one script to read the source cells and their formatting, build people, histories and requests, and write the proposal YAML. Determine each request weight from that cell's formatting and the user's stated policy. Do not copy parsed values into handwritten YAML. Keep `at most one shift per day` in every rebuilt schedule, including imports that request no optional scheduling rules.
