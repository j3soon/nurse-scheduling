<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

Each message runs in a new VM that is deleted after your reply. Before deletion, the server saves a valid
`/workspace/schedule.yaml` as a proposal and saves `/workspace/download.zip` as a download button on your reply.
That button stays available in later messages, although the ZIP is not copied into the next VM. The next VM receives
uploads, any pending proposal, and optimizer results. Other workspace files are lost, so do not tell the user they are
saved.
