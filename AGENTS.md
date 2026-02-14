# Repository Guidelines

## Project Structure & Module Organization
- `core/`: Python scheduling engine and API.
  - `core/nurse_scheduling/`: CLI, scheduler, data models, exporter, FastAPI server (`serve.py`).
  - `core/tests/`: pytest suites and YAML/CSV test fixtures under `core/tests/testcases/`.
- `web-frontend/`: Next.js + TypeScript app (App Router).
  - `web-frontend/src/app/`: route pages.
  - `web-frontend/src/components/`, `src/hooks/`, `src/utils/`, `src/types/`: shared UI logic and utilities.
- `docs/`: MkDocs source and overrides.
- `thirdparty/`: external calendar data and helper scripts.

## Build, Test, and Development Commands
- Frontend (from `web-frontend/`):
  - `bun install`: install JS dependencies.
  - `bun run dev`: run local dev server.
  - `bun run build`: production build.
  - `bun run lint`: run ESLint (also used in CI).
- Core (from `core/`):
  - `uv venv --python 3.12 && source .venv/bin/activate`: create/activate venv.
  - `uv pip install -r requirements.txt`: install Python deps.
  - `python -m nurse_scheduling.cli <input.yaml> [output.csv]`: run scheduler CLI.
  - `pytest --log-cli-level=DEBUG tests/test_schedule.py tests/test_serve.py`: run core tests.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` for functions/modules, `PascalCase` for classes, keep type names explicit.
- TypeScript/React: component files and components in `PascalCase`; hooks prefixed with `use`.
- Linting: frontend uses `next/core-web-vitals` + TypeScript rules via `web-frontend/eslint.config.mjs`.
- Keep file endings clean: no trailing spaces; newline at end of file.

## Testing Guidelines
- Framework: `pytest` for core and backend tests.
- Main suites: `core/tests/test_schedule.py`, `core/tests/test_serve.py`.
- Add new scheduling cases as fixture pairs in `core/tests/testcases/**` (typically `.yaml` input with matching `.csv` or `.txt` expected output).
- Run affected tests locally before opening a PR.

## Commit & Pull Request Guidelines
- Follow Conventional Commits as seen in history, e.g. `feat(core/serve): ...`, `fix(web-frontend): ...`, `refactor(core): ...`.
- Keep commits focused by module (`core`, `web-frontend`, `docs`).
- PRs should include:
  - clear scope and rationale,
  - linked issue(s) when applicable,
  - test/lint evidence (commands + results),
  - screenshots for frontend UI changes.
