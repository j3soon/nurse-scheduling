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
- Reference actions by release tag, not by commit SHA. This project does not
  need the extra supply-chain protection of a SHA pin. Use the major-version
  tag, such as `actions/checkout@v4`, when the action publishes one. Otherwise
  use the exact release tag, such as `astral-sh/setup-uv@v10.4.0`.
- Install core Python dependencies with `astral-sh/setup-uv` and
  `uv sync --locked`. Pin uv to the version that the Dockerfiles copy.
  Set `working-directory: core` and `activate-environment: true`, so later
  steps run `python` and the tools from `core/.venv`.
- Give each install set its own `cache-suffix`: `all-extras` for core tests,
  `runtime` for `--no-dev`, and `lint` for lint-only jobs. Jobs with the same
  cache key share one saved cache, so a smaller set must not save it first.
- Lint-only jobs install only the tools they run, with `--only-group lint`.
- Keep the full solver profile and a bounded new real-scenario search in weekly
  checks on Linux, macOS, and Windows. Routine checks use the primary profile
  and the fixed-assignment replay. Scheduled checks run on the default branch.
