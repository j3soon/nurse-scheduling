<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When the user explicitly asks to replace the entire schedule with an uploaded YAML,
copy that file to `/workspace/schedule.yaml` with `bash`. Do not print or rewrite
the whole file just to import it. Inspect a bounded summary if needed. The server
checks the copied schedule and produces a proposal for approval. For a partial
update, keep the current schedule and change only the requested fields.
