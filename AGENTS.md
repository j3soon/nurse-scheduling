# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: MkDocs source and overrides.
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
- Derive Git versions on the host for local Docker builds. Do not copy `.git`
  into build contexts because linked worktrees store metadata elsewhere.
- Record durable, generally applicable user guidance in the nearest relevant
  `AGENTS.md`. Omit task-specific or temporary details.
- Note potentially wasteful token use and uninformative tests, scripts, or runs.
  Fix them when practical, otherwise report or document them for review.
- Use Conventional Commits, scoped by module where applicable, for example:
  `feat(core/serve): ...`, `fix(web-frontend): ...`, or `docs: ...`.
- For Codex-created commits, include a descriptive body that ends with a
  separate `by Codex` line.
- Build multi-paragraph commit messages with separate `git commit -m`
  arguments. Do not embed escaped `\n` sequences because Git stores them
  literally instead of converting them to newlines.

## Comment and Documentation Style
- Keep comments and documentation minimal, concise, yet informative.
- Do not use em-dash or semicolon to connect sentences.

## Cross-Module Requirements
- When renaming or deleting frontend people, dates, or shift types, sync all
  references, including preferences and export layout entries.

## Pull Requests
Include scope and rationale, linked issues when applicable, test/lint evidence,
and screenshots for frontend UI changes.
