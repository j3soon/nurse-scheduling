# Frontend Guidelines

The app uses the Next.js App Router. Shared code lives under `src/components/`,
`src/hooks/`, `src/utils/`, and `src/types/`.

## Commands
Run commands from `web-frontend/`:

- `bun install --frozen-lockfile`
- `bun run dev`
- `bun run build`
- `bun run lint -- --fix`
- `bun run test:affected`: quietly reconcile dependencies and run tests
  related to uncommitted `src/` changes with compact output; shared test config
  and deleted source files trigger the compact full unit/component suite.
- `bun run test`: run the full unit/component suite.
- `bun run test:e2e`: run Playwright integration tests.
- `bun run test:e2e:affected`: run changed or explicitly provided E2E specs
  with compact output and stop after the first failure.

Use `bun run test:affected` for routine changes. Run the full unit/component
and browser suites when checking the full app or broad shared behavior.
Frontend unit/component tests use Vitest; browser integration tests use
Playwright.
`test:e2e:affected` does not infer browser coverage from changed `src/` files;
pass relevant E2E spec paths explicitly when validating frontend behavior.

Keep commit bodies focused on behavior and rationale. Do not mention routine
test additions or regression coverage unless the test strategy itself is
material to the change.

To test specific source files from the repository root, run:

```sh
./scripts/test_frontend_affected.sh web-frontend/src/path/to/file.ts
```

## TypeScript And React Style
- Use `PascalCase` for component files and components.
- Prefix hooks with `use`.
- Follow the existing Next.js App Router and shared-code patterns under `src/`.
- ESLint uses `next/core-web-vitals` plus TypeScript rules from
  `eslint.config.mjs`.
- Every frontend test file (`*.test.ts` and `*.test.tsx`) must include the AGPL
  header documented in `../docs/agent-license-headers.md`.
