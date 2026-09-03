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
- Store screenshots and other disposable review output in the Git-ignored repository-root `artifacts/`.
- Derive Git versions on the host for local Docker builds. Never copy `.git` into build contexts (linked worktrees store metadata elsewhere).
- Note wasteful token use and uninformative tests, scripts, or runs. Fix when practical, otherwise report or document.
- Record durable, general user guidance in the nearest relevant `AGENTS.md`. Omit task-specific or temporary details.

## Git
- Preserve each file's staged or unstaged state. Never stage, unstage, or commit unless explicitly asked. Stage only the requested index entries.
- Keep commits focused by module (`core`, `web-frontend`, or `docs`). A `core` + `web-frontend` change may share one commit.
- Use Conventional Commits, module-scoped where applicable, e.g. `feat(core/serve): ...`, `fix(web-frontend): ...`, `docs: ...`.
- Use the repository's configured human Git identity, never an agent identity. If none is configured, ask the user.
- Agent-created commits need a descriptive body ending with a `by <Harness> (<Model>)` line using the actual harness and model names, e.g. `by Codex (gpt-5.6-sol)` or `by Claude Code (Opus 5)`.
- For Codex attribution, use the full canonical lowercase model slug, such as `gpt-5.6-sol`. Never substitute a shortened family name such as `GPT-5`.
- Keep commit bodies short, at most two brief paragraphs covering why the change was needed and what it does. Document mechanism, investigation notes, and third-party behavior in Markdown instead.
- Build multi-paragraph messages with separate `git commit -m` arguments. Never embed escaped `\n` sequences, which Git stores literally.

## Style
- Keep comments and docs minimal, concise, yet informative.
- Do not use em-dash or semicolon to connect sentences.

## Cross-Module Requirements
- When renaming or deleting frontend people, dates, or shift types, sync all references, including preferences and export layout entries.

## Pull Requests
- Include scope and rationale, linked issues when applicable, test/lint evidence, and screenshots for frontend UI changes.
