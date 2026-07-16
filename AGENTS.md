# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: MkDocs source and overrides.
- `scripts/`: setup and development utilities.
- `thirdparty/`: external calendar data and helpers.

Before modifying core or frontend files, read the module-specific commands and
conventions in `core/AGENTS.md` or `web-frontend/AGENTS.md`.

## Shared Workflow
- For Linux environment setup, run `./scripts/setup_env.sh`.
- Keep edits scoped to the requested module and preserve existing patterns.
- Keep commits focused by module (`core`, `web-frontend`, or `docs`).
- Keep file endings clean: no trailing spaces and a newline at end of file.
- Run affected tests and lint checks before finishing.
- Use Conventional Commits, scoped by module where applicable, for example:
  `feat(core/serve): ...`, `fix(web-frontend): ...`, or `docs: ...`.

## Comment and Documentation Style
- Keep comments and documentation minimal, concise, yet informative.
- Do not use em-dash or semicolon to connect sentences.

## Cross-Module Requirements
- When changing frontend rename/delete behavior for people, dates, or shift
  types, keep all references in sync, including preferences and export layout
  entries.

## Pull Requests
Include scope and rationale, linked issues when applicable, test/lint evidence,
and screenshots for frontend UI changes.
