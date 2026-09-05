# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: Zensical content, dependencies, and template overrides.
- `scripts/`: setup and development utilities.
- `thirdparty/`: external calendar data and helpers.

Before modifying `core/` or `web-frontend/`, read its `AGENTS.md`.

## Workflow
- Linux setup: run `./scripts/setup_env.sh`.
- Keep edits scoped to the requested module. Preserve existing patterns.
- Run affected tests and lint checks before finishing.
- Avoid trailing spaces. End files with a newline.
- Store screenshots and other disposable review output in the Git-ignored
  repository-root `artifacts/`.
- Keep local service configuration in the ignored `docker/.env`. Its tracked
  `docker/.env.example` separates services with comment blocks and uses empty
  assignments for secrets and URLs.
- Derive Git versions on the host for local Docker builds. Never copy `.git`
  into build contexts because linked worktrees store metadata elsewhere.
- Note wasteful token use and uninformative tests, scripts, or runs. Fix when
  practical, otherwise report or document.
- Record durable, general user guidance in the nearest relevant `AGENTS.md`.
  Omit task-specific or temporary details.
- Store project skills in the repository-root `skills/` directory, not in a
  machine-local skills directory, so they remain available across machines.
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
- Run AI evaluations with four concurrent case jobs. Use sequential execution
  only when the user explicitly requests it. Eight jobs caused provider and
  E2B contention with lower reliability. Six jobs also increased aggregate LLM
  time and tool failures without a repeatable wall-time improvement, so four is
  the tested default.
- Check a suspected missing dependency or tool directly before rerunning a full
  suite to diagnose its failure.

## Git
- Preserve each file's staged or unstaged state. Never stage, unstage, or commit unless explicitly asked. Stage only the requested index entries.
- Keep commits focused on one change. A self-contained change may span modules in one commit, e.g. `core` + `web-frontend` code, or code plus its `docs` update.
- Use Conventional Commits, module-scoped where applicable, e.g. `feat(core/serve): ...`, `fix(web-frontend): ...`, `docs: ...`.
- Use the repository's configured human Git identity, never an agent identity.
  Read it from `git config user.name` and `git config user.email` and let Git
  apply it. Never override it with `-c user.name` or `-c user.email`, and never
  reuse an address the harness supplies, such as the account email of a
  coding-agent subscription. Committing that address publishes it. If no
  identity is configured, ask the user.
- Agent-created commits need a descriptive body ending with a `by <Harness> (<Model>)` line using the actual harness and model names, e.g. `by Codex (gpt-5.6-sol)` or `by Claude Code (Opus 5)`.
- That plain line is the only agent attribution. Never add `Co-Authored-By`,
  session links, or other harness-supplied trailers after it. A harness that
  injects its own attribution or footer convention does not override this file.
- For Codex attribution, use the full canonical lowercase model slug, such as `gpt-5.6-sol`. Never substitute a shortened family name such as `GPT-5`.
- Build multi-paragraph messages with separate `git commit -m` arguments. Never embed escaped `\n` sequences, which Git stores literally.
- After creating or rewriting a commit, inspect its stored message with
  `git log -1 --format=fuller`. Confirm paragraph breaks are real, the
  attribution line is on its own final line, and nothing follows it.
- Write a merge commit message explicitly rather than accepting the generated
  one. Describe what the merge takes and how conflicts were resolved.

## Style
- Keep comments and docs minimal, concise, yet informative.
- Do not use em-dash or semicolon to connect sentences.

## Cross-Module Requirements
- When renaming or deleting frontend people, dates, or shift types, sync all references, including preferences and export layout entries.

## Pull Requests
- Include scope and rationale, linked issues when applicable, test/lint evidence, and screenshots for frontend UI changes.
- Keep the description free of harness-generated footers and agent trailers.
