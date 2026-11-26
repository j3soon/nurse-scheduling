# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: Zensical content, dependencies, and template overrides.
- `scripts/`: setup and development utilities.
- `thirdparty/`: external data, helpers, and vendored libraries shared by modules.

Before modifying `core/` or `web-frontend/`, read its `AGENTS.md`.

## Environment
- Detect the session location first:
  `test -f /.dockerenv && echo container || echo host`.
- Dev container (`/.dockerenv` exists, built from `docker/Dockerfile.dev*`):
  the main clone mounts at `/app`. The image installs the locked core
  packages in `/opt/venv`, which is active and first on `PATH`. Run `python`,
  `pytest`, `ruff`, and `ty` directly. Do not run `./scripts/setup_env.sh` or
  create another virtual environment. After `core/uv.lock` changes, run
  `uv sync --active --locked --all-extras` in `core/`. Pass `--active` to
  `uv sync` and `uv run`, because otherwise uv creates `core/.venv` in the
  host checkout. CI, the dev images, and the API images run Python 3.14.
- Prefer APT packages from the distribution or the tool project's documented
  package repository over custom source builds in development images.
- Host checkout (no `/.dockerenv`): the repository lives wherever the user
  cloned it. Run `./scripts/setup_env.sh` for the initial Linux setup and
  follow each module's virtual-environment guidance.
- Resolve the repository root with `git rev-parse --show-toplevel` instead of
  assuming `/app` or a home-directory path. Never hardcode one
  environment's absolute paths in scripts, skills, or documentation.
- Host tools such as Docker, Compose, SSH keys, and browser profiles may be
  absent or different inside a dev container. Check `command -v` before using
  them, and remember that `127.0.0.1` differs between the two environments.

## Workflow
- Keep CI enabled on every push, including feature branches before a pull
  request exists. Preserve both push and pull-request checks when reducing
  CI runtime. Do not restrict push triggers to selected branches or tags.
- AI testing transition: use `core/tests/ai/` for minimal, human-reviewed,
  quick AI tests. `core/tests/ai_eval/` is legacy. Do not run, extend, repair,
  or remove legacy AI tests in this branch. This takes precedence over older
  legacy evaluation instructions in module guidance and skills.
  After this branch is completed and merged, use a dedicated removal branch
  to delete the legacy tests and their scripts, CI checks, documentation, and
  evidence references. Remove this transition note and outdated legacy
  guidance when that cleanup is complete.
- Dev containers have no SSH key, so `git fetch` and `git push` through an SSH
  `origin` fail. Fetch from the HTTPS URL, such as
  `git fetch https://github.com/j3soon/nurse-scheduling.git dev`, and compare
  with `FETCH_HEAD`. Ask the user to push from the host.
- Dev containers authenticate GitHub CLI with `GH_TOKEN` when the host exports
  it, as `README.md` describes. If `gh auth status` reports no login, read the
  public repository through the GitHub REST API with `curl`. Unauthenticated
  requests are limited to 60 per hour, so batch them and save the responses.
  They cannot use GraphQL, which reports review thread resolution. For public
  job logs, try the per-job download endpoint in `skills/fix-github-ci`.
  If log access is denied, reproduce the failing CI step locally or ask the
  user to restart the container with `GH_TOKEN`.
- For concurrent agent edits, mount the main clone at `/app` and create one
  checkout per agent with `scripts/add_worktree.sh TYPE/NAME [BASE_REF]`.
  Use a branch prefix that describes the change, such as `fix/`, `feat/`,
  or `docs/`. The helper creates `.worktrees/TYPE/NAME` with relative Git
  links and requires Git 2.48+ on both host and container. Do not mount a linked
  checkout alone, because its shared Git metadata lives outside that mount.
  Each agent owns its branch and worktree. The coordinating agent reviews and
  integrates completed commits, then removes clean checkouts with
  `scripts/remove_worktree.sh TYPE/NAME`. Do not reset another agent's branch
  or delete its work. Keep dependencies and build output separate per
  worktree, choose distinct service ports, and load shared secrets from the
  main clone's ignored env file.
- The worktree helpers copy the main clone's `docker/.env.staging` into new
  checkouts. When `scripts/remove_worktree.sh` stops with exit code 3, the
  checkout changed that file. Show the user the listed setting names and ask
  whether to update the main copy. Then rerun with `--update-env-staging` or
  `--keep-env-staging`. Never choose for the user.
- Keep edits scoped to the requested module. Preserve existing patterns.
- When resuming another agent's session, verify compatibility claims and pending
  check results against current code, configuration, and saved outputs. Treat
  the handoff summary as a lead to investigate.
- Run affected tests and lint checks before finishing.
- Avoid trailing spaces. End files with a newline.
- Several docs pages are symbolic links. Edit the link target, because `sed -i`
  and similar in-place rewrites replace a link with a regular file.
- Store screenshots and other disposable review output in the Git-ignored
  repository-root `artifacts/`.
- Keep local service configuration in the ignored `docker/.env`. Its tracked
  `docker/.env.example` separates services with comment blocks and uses empty
  assignments for secrets and URLs.
  When exposing a setting through Compose, update every supported Compose
  variant and its environment file example together.
- Derive Git versions on the host for local Docker builds. Never copy `.git`
  into build contexts because linked worktrees store metadata elsewhere.
- Note wasteful token use and uninformative tests, scripts, or runs. Fix when
  practical, otherwise report or document.
- Record durable, general user guidance in the nearest relevant `AGENTS.md`.
  Omit task-specific or temporary details.
- Store project skills in the repository-root `skills/` directory, not in a
  machine-local skills directory, so they remain available across machines.
- Store agent notes and memory in the repository, in the nearest relevant
  `AGENTS.md` or a skill. Never write machine-local agent memory, such as
  Claude Code memory under `~/.claude/projects/`. Recloning the repository or
  moving it to another machine erases those notes.
- After finishing a task, suggest improvements to `AGENTS.md`, skills, scripts,
  or other agent-facing configuration when the task exposed one. Propose only
  guidance that generalizes to recurring work. Keep session-specific findings in
  the commit message instead.
- For model prompt, schema reference, or other AI guidance changes motivated by
  an evaluation, name the relevant testcase in the commit body and briefly
  record the before and after behavior or trajectory. Before removing or
  consolidating that guidance, use Git blame or history to recover its rationale
  and rerun the named testcase to check for regression.
- Inspect the repository with narrow queries. Filter to the paths, revisions, or
  lines in question instead of listing every branch, printing whole files, or
  dumping full status output.
- Compare versions of a file by searching each revision for the differing value
  instead of printing every version in full.
- Prefer the compact or affected test and lint commands documented for each
  module. Read the summary lines of a run before requesting more output.
- Treat full local CI and a full AI evaluation as long-running checks. When the
  agent runtime supports yielded background execution with a completion
  notification, let that background worker own the process wait, preserve the
  exit code and compact output, and notify the active agent once when the check
  finishes. Continue the same task from that notification instead of polling
  from model turns. Keep affected checks and selected evaluation cases in the
  foreground.
- Let the AI evaluation runner discover concurrency from provider deployment
  limits and cached health, capped at 20 case jobs for E2B Hobby. Use `--jobs`
  only to request a lower limit. Inspect `concurrency.json` for the chosen limit
  and fallback reason. Reuse the AI provider URL and credentials for LiteLLM
  model metadata and cached health checks.
  Check capacity with `scripts/check_litellm_concurrency.sh` before comparing
  performance across runs.
- Check a suspected missing dependency or tool directly before rerunning a full
  suite to diagnose its failure.
- Run security scans with `skills/security-scan` against an isolated loopback
  copy of the services. Never scan the public domain or the running deployment.
- Upgrade dependencies with `skills/upgrade-dependencies`. Unless the user says
  otherwise, give each upgrade its own worktree and pull request.
- When upgrading cuOpt or OR-Tools, require passing correctness tests and
  comparable or better performance on representative real Schedule Specs.
  Run the old and new versions on the same hardware with the same inputs,
  solver settings, and time budgets. Compare time to a fixed quality target
  and the score reached within the budget. Repeat nondeterministic runs and
  record both correctness and performance evidence in the upgrade pull request.
  Use [benchmark-solvers](skills/benchmark-solvers/SKILL.md) for paired
  real-case comparisons of solver versions or model formulations.
- Diagnose hanging backend requests with `skills/debug-backend-hangs`. A browser
  CORS error for the APIs can mean the origin never responded, so isolate the
  hop before changing CORS or proxy configuration.

## Git
- Never commit directly on `dev`. Before editing, check the current branch and
  switch to a feature branch or create a worktree on one.
- Commit validated implementation work as part of the task unless the user asks
  to leave it uncommitted. Inspection and planning requests do not authorize
  implementation changes.
- For a series of independent improvements, commit each completed improvement
  after its affected checks pass and any required evaluation evidence is saved.
  Create that self-contained commit before starting the next improvement,
  unless the user asks to leave changes uncommitted.
- Inspect staged and unstaged changes before committing. Stage or unstage entries
  as needed to keep the commit within the task's scope. Preserve unrelated work.
- Keep each commit self-contained. Include one complete change with its necessary
  implementation, representative usage, tests, and documentation. A single change
  may span modules, such as `core` + `web-frontend`, or code plus its `docs` update.
- Prefer reviewable feature slices over minimal implementation-step commits.
  Separate changes only when each can be understood, validated, and reverted
  independently.
- Keep AGENTS.md and skill clarifications with the related implementation or
  skill change. Do not create a separate commit solely to restate an existing
  workflow rule. Use a standalone guidance commit only when it introduces an
  independently useful policy with no related change in the active series.
- Fold minor whitespace, wording, marker, or metadata corrections into the
  related commit. Do not create standalone cleanup commits for them. Authorization
  to commit an active unpublished series includes these minor local rewrites.
  Require explicit rewrite authorization for published history or commits outside
  that series.
- When validation and committing share a shell command, stop on any failed check
  so it cannot proceed to a commit.
- Use Conventional Commits, module-scoped where applicable, e.g. `feat(core/serve): ...`, `fix(web-frontend): ...`, `docs: ...`.
- Choose the commit type by what changes. Use `feat` for new capabilities or
  intended agent behavior, even when they also reduce tokens or time. Reserve
  `perf` for efficiency improvements that preserve existing behavior.
- Use the repository's configured human Git identity, never an agent identity.
  Read it from `git config user.name` and `git config user.email` and let Git
  apply it. Never override it with `-c user.name` or `-c user.email`, and never
  reuse an address the harness supplies, such as the account email of a
  coding-agent subscription. Committing that address publishes it. If no
  identity is configured, ask the user.
- Agent-created commits need a descriptive body ending with a `by <Harness> (<Model>)` line using the actual harness and model names, e.g. `by Codex (gpt-5.6-sol)` or `by Claude Code (Opus 5)`.
- For Codex attribution, use the full lowercase model slug, such as `gpt-5.6-sol`. Never substitute a shortened family name such as `GPT-5`.
- Keep commit bodies short, at most two brief paragraphs covering why the change was needed and what it does. Document mechanism, investigation notes, and third-party behavior in Markdown instead.
- A commit that changes a lock names each bun or uv command and the files that
  it wrote, such as `` `cd core && uv lock` updates `core/uv.lock`. `` Give a
  reason only for a version changed by hand in `package.json` or
  `pyproject.toml`. Omit hand edits of files that no tool owns, because the
  diff shows them. Follow the format in `skills/upgrade-dependencies`, and
  check it with that skill's `check_upgrade_commits.py`.
- Make commit descriptions understandable without chat history or discarded
  revisions. Name previous scripts or explain previous behavior when comparing
  implementations. After amending, folding, or rewriting history, check affected
  messages against their parent commits in the rewritten history. Replace labels
  whose meaning depends on removed commits or implementations with a concrete
  description of that behavior.
- That plain line is the only agent attribution. Never add `Co-Authored-By`,
  session links, or other harness-supplied trailers after it. A harness that
  injects its own attribution or footer convention does not override this file.
- Choose the model actually running the commit for the attribution line. Codex
  may use `gpt-6-sol` or `gpt-6-astra`. Select the matching full lowercase
  slug rather than inferring it from task difficulty or available model lists.
  Pi, Claude Code, and Antigravity CLI must use their own active harness and
  model names. If the active model is unclear, verify it before committing.
  Never substitute a shortened family name such as `GPT-5`.
- When a commit ports or reworks another agent's change, name each harness in
  the same line, such as `by Antigravity (Gemini 4 Neon) and Claude Code (Opus 5.5)`.
- Include validation details in a commit body only when they materially help a
  reviewer assess the change, such as a regression reproduction, an unusual check,
  or a known limitation. Omit routine successful-test and lint summaries. Keep
  routine verification in review reports or the final response.
- Build multi-paragraph messages with separate `git commit -m` arguments. Never embed escaped `\n` sequences, which Git stores literally.
- Do not cite timestamp-named files or directories under the ignored `artifacts/` directory in commit messages. Record durable evaluation evidence with case names, pass rates, and configuration instead.
- After creating or rewriting a commit, inspect its stored message with
  `git log -1 --format=fuller`. Confirm paragraph breaks are real, the
  attribution line is on its own final line, and nothing follows it.
- When folding a validated code change into an earlier commit, check that the
  final rewritten tree matches the tested candidate. Also inspect the amended
  commit against its parent to confirm that abandoned configuration changes are
  absent. Preserve unrelated working changes and remote refs unless their
  modification is explicitly authorized.
- Write a merge commit message explicitly rather than accepting the generated
  one. Describe what the merge takes and how conflicts were resolved.

## Style
- Keep comments and docs minimal, concise, yet informative.
- Keep the root README focused on setup and usage for users. Put CI details in
  the relevant module documentation.
- Use plain technical English, inspired by ASD-STE100, in prompts, docs,
  commit descriptions, and replies. State the problem or task first. Use active
  voice, concrete verbs, and one main idea per sentence. Use the same term for
  the same concept. Explain necessary technical terms on first use and preserve
  exact code identifiers. Formal ASD-STE100 compliance is not required.
- Prefer complete, short sentences over compressed phrases. Write "check that
  the saved data matches the current YAML" instead of "apply a current-source
  freshness guard." Keep detailed mechanisms and evaluation bookkeeping in
  supporting docs. Before finishing, read the text without the conversation
  and check that the problem, action, and result are clear.
- Name the schedule's role or format directly, such as "current Schedule Spec,"
  "original schedule," "validated Schedule Spec," or "backend Schedule Spec format."
  Name the specific property of other values too, such as "normalized
  selector" or "compiled selector." `scripts/check_terminology.sh` rejects
  vague jargon that hides it, and CI runs the check.
- Use **Schedule Spec** for input defining people, dates, shift types, constraints,
  preferences, and export settings. Use the same term in GUI labels and technical
  prose. Use `ScheduleSpec`, `schedule_spec`, and `scheduleSpec` in code.
- Use **Schedule** for output containing actual shift assignments, whether made
  by the optimizer or by hand. Fixed assignments in a Schedule Spec are input
  constraints. Use "schedule" for the output without redundant terms such as
  "schedule results" or "optimized schedule", unless its origin matters.
- Name file formats when relevant: "Schedule Spec YAML" and "schedule as XLSX".
  Use "workbook" for spreadsheet file operations.
  Use "empty Schedule Spec" for empty input and "source materials" for documents
  that have not yet been interpreted into a Schedule Spec.
- Follow [Deployment and Compatibility](docs/content/developer-guide/compatibility.md).
  Every push to `dev` replaces all services together. Keep tagged release
  frontends compatible with newer optimizer backends. Automatically migrate
  browser Schedule Specs, history used by Undo/Redo, and settings. Experimental
  AI conversations, sessions, and chat history have no upgrade compatibility
  guarantee. Current frontend code need not support older backends.
- Isolate required tagged-frontend adapters and browser migrations in dedicated
  `compat.py`, `compat.ts`, or `compat/` modules. Current callers and writers use
  current names and formats. Keep legacy fixtures in their original format.
  Test migration failure and preservation of user content. Avoid adapters for
  unsupported Python imports, AI protocols, or developer-tool export formats.
- When reporting validation, lead with what passed. Separate correctness checks
  from performance measurements, and limit each caveat to the claim it affects.
  If test input changed, say which checks were repeated and which measurements
  still need confirmation. Do not imply that a working feature is unvalidated
  because its performance numbers have not been measured again.
- Do not use em-dash or semicolon to connect sentences.
- Mark every new file written entirely by an AI coding agent, tests included, with the
  module's marker comment immediately after the license block. Adding to a file a person
  wrote does not earn one.

## Cross-Module Requirements
- When renaming or deleting frontend people, dates, or shift types, sync all references, including preferences and export layout entries.
- Change Python dependencies with `uv add`, `uv remove`, or
  `uv lock --upgrade-package NAME` in the module directory. Commit
  `pyproject.toml` with its `uv.lock`. Installers read the lock, so a version
  change needs no installer edits. When a package moves between the runtime
  set, an extra, and a dependency group, check the `uv sync` flags in the
  `docker/` images, the GitHub workflows, and `scripts/setup_env.sh`.
- Change frontend dependencies, including `overrides`, with `bun add`,
  `bun remove`, `bun update`, or `bun pm pkg set` in `web-frontend/`. Commit
  `package.json` with its `bun.lock`.
- Toolchain versions, action tags, and image tags repeat across files. Update
  every location that `skills/upgrade-dependencies/scripts/dependency_inventory.py`
  lists. CI rejects conflicting pins.

## Pull Requests
- Include scope and rationale, linked issues when applicable, test/lint evidence, and screenshots for frontend UI changes.
- Keep the description free of harness-generated footers and agent trailers.
