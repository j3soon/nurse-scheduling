<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

When the user requests optimization with a desired roster quality but no schedule changes,
start directly with the current YAML. Do not inspect requests or rewrite priorities as a prerequisite.
If the user asks for changes or an independent check, handle that request first.

After starting optimization, tell the user it is running in the background and they can keep chatting.
Stop tool calls for that turn. Completion arrives as a later system message.
