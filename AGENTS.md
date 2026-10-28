# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: Zensical content, dependencies, and template overrides.
- `scripts/`: setup and development utilities.
- `thirdparty/`: external calendar data and helpers.

Before modifying `core/` or `web-frontend/`, read its `AGENTS.md`.

## Environment
- Detect the session location first:
  `test -f /.dockerenv && echo container || echo host`.
- Dev container (`/.dockerenv` exists, built from `docker/Dockerfile.dev*`):
  the checkout mounts at `/workspace`, and module dependencies come
  preinstalled system-wide. Do not run `./scripts/setup_env.sh`, install
  `uv`, or create a virtual environment. Run `python`, `pytest`, and `ruff`
  directly. In the cuOpt image, `python3` is the base 3.10 interpreter
  without project packages, so use `python`, which is Python 3.14 while CI
  uses 3.12.
- Host checkout (no `/.dockerenv`): the repository lives wherever the user
  cloned it. Run `./scripts/setup_env.sh` for the initial Linux setup and
  follow each module's virtual-environment guidance.
- Resolve the repository root with `git rev-parse --show-toplevel` instead of
  assuming `/workspace` or a home-directory path. Never hardcode one
  environment's absolute paths in scripts, skills, or documentation.
- Host tools such as Docker, Compose, SSH keys, and browser profiles may be
  absent or different inside a dev container. Check `command -v` before using
  them, and remember that `127.0.0.1` differs between the two environments.

## Workflow
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
- Diagnose hanging backend requests with `skills/debug-backend-hangs`. A browser
  CORS error for the APIs can mean the origin never responded, so isolate the
  hop before changing CORS or proxy configuration.

## Git
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
- Name the schedule's role or format directly, such as "current schedule,"
  "original schedule," "validated schedule," or "backend schedule format."
  Name the specific property of other values too, such as "normalized
  selector" or "compiled selector." `scripts/check_terminology.sh` rejects
  vague jargon that hides it, and CI runs the check.
- Use "schedule" as the umbrella term for the roster in any state. Name the
  browser-kept YAML input "schedule data" (排班資訊) and the optimizer output
  "optimized schedule" (排好的班). Name the state with daily assignments
  completed, whether by the optimizer or by hand, "completed schedule". Name
  the format at API and code boundaries,
  such as "schedule YAML" or "XLSX artifact," because "result" already means a
  job's outcome and score. Avoid "schedule config": `ExportConfig` and solver
  options already own "config." Name the zero-content state of the input
  "empty schedule data" and the ward's scattered, not-yet-interpreted
  documents "source materials."
- Use "schedule data" for YAML files and "schedule workbook" for XLSX files.
  Describe XLSX-to-YAML imports as "build schedule data from an XLSX workbook."
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
- When adding, moving, or removing a dependency, update every installer in the
  same commit: the `docker/` images, the GitHub workflows, `scripts/setup_env.sh`,
  the affected-test selection in `scripts/`, and the `README.md` and `docs/`
  install commands. Grep for the file name rather than the package name, since
  an installer usually names only the requirements file.

## Pull Requests
- Include scope and rationale, linked issues when applicable, test/lint evidence, and screenshots for frontend UI changes.
- Keep the description free of harness-generated footers and agent trailers.
