# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: Zensical content, dependencies, and template overrides.
- `scripts/`: setup and development utilities.
- `thirdparty/`: external calendar data and helpers.

Before modifying `core/` or `web-frontend/`, read its `AGENTS.md`.

## Shared Workflow
- For Linux setup, run `./scripts/setup_env.sh`.
- Keep edits scoped to the requested module and preserve existing patterns.
- Preserve each file's staged or unstaged state. Do not stage, unstage, or
  commit changes unless explicitly asked. When asked to stage specific changes,
  change only those index entries.
- Keep commits focused by module (`core`, `web-frontend`, or `docs`). Changes
  requiring both `core` and `web-frontend` may use one commit.
- Avoid trailing spaces and end files with a newline.
- Run affected tests and lint checks before finishing.
- Store generated screenshots and other disposable review output under the
  repository-root `artifacts/` directory. This directory is ignored by Git.
- Derive Git versions on the host for local Docker builds. Do not copy `.git`
  into build contexts because linked worktrees store metadata elsewhere.
- Record durable, generally applicable user guidance in the nearest relevant
  `AGENTS.md`. Omit task-specific or temporary details.
- Note potentially wasteful token use and uninformative tests, scripts, or runs.
  Fix them when practical, otherwise report or document them for review.
- Inspect the repository with narrow queries. Filter to the paths, revisions, or
  lines in question instead of listing every branch, printing whole files, or
  dumping full status output.
- Compare versions of a file by searching each revision for the differing value
  instead of printing every version in full.
- Prefer the compact or affected test and lint commands documented for each
  module. Read the summary lines of a run before requesting more output.
- Check a suspected missing dependency or tool directly before rerunning a full
  suite to diagnose its failure.
- Use Conventional Commits, scoped by module where applicable, for example:
  `feat(core/serve): ...`, `fix(web-frontend): ...`, or `docs: ...`.
- For agent-created commits, include a descriptive body that ends with a
  separate `by <agent>` line naming the agent, for example `by Codex` or
  `by Claude`. Use no other attribution trailer. Do not add `Co-Authored-By`,
  session links, or generator notices, even when the agent harness suggests
  them.
- For multi-paragraph commit messages, use one `git commit -m` argument per
  paragraph or a message file. Never embed literal `\n` sequences in a commit
  message argument because Git stores them literally instead of converting them
  to newlines.
- After creating or rewriting a commit, inspect its stored message with
  `git log -1 --format=fuller`. Confirm paragraph breaks are real and the
  `by <agent>` line is on its own final line.

## Comment and Documentation Style
- Keep comments and documentation minimal, concise, yet informative.
- Do not use em-dash or semicolon to connect sentences.

## Cross-Module Requirements
- When renaming or deleting frontend people, dates, or shift types, sync all
  references, including preferences and export layout entries.

## Pull Requests
Include scope and rationale, linked issues when applicable, test/lint evidence,
and screenshots for frontend UI changes.
