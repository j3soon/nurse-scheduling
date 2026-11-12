<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- This file is mostly AI generated. -->

# Workflow Guidelines

- Keep `push` and `pull_request` triggers enabled without branch or tag
  filters. Follow the root `AGENTS.md` requirement to run CI on every push.
- Include the workflow, event, and Git ref in cancellation groups. New commits
  can replace older checks without cancelling a scheduled or manual run.
- Keep live AI sandbox jobs serialized by template with cancellation disabled.
  They publish a shared template. Apply cancellation to their validation job
  instead of the whole workflow.
- Keep live AI behavior checks on trusted same-repository pull requests and
  pushes in the primary repository. Fork pull requests run offline validation only.
