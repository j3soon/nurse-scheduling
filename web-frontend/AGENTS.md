# Frontend Guidelines

The app uses the Next.js App Router. Shared code lives under `src/components/`,
`src/hooks/`, `src/utils/`, and `src/types/`.

## Commands
Run commands from `web-frontend/`. Basic dev, build, lint, unit, and E2E
commands are documented in `README.md`.

- `bun install --frozen-lockfile`
- `bun run test:affected`: reconcile dependencies, lint the full frontend, and
  run tests related to uncommitted `src/` changes with compact output. Shared
  config and deleted source files trigger the full unit/component suite. An
  unmatched source path fails instead of passing with zero tests.
- `bun run test:e2e:affected`: lint the full frontend and run changed or
  explicitly provided E2E specs with compact output on an isolated server.
  Stop after the first failure.

Use `bun run test:affected` for routine changes. Run the full unit/component
and browser suites when checking the full app or broad shared behavior.
Frontend unit/component tests use Vitest; browser integration tests use
Playwright.
Both affected commands accept `--base REF` to include committed branch changes
since the merge base with `REF`, `--list` to inspect selection, and `--full` to
run their whole suite. `test:e2e:affected` cannot infer browser coverage from
changed app source or public assets. Without explicit spec paths or `--full`,
it fails rather than silently skipping those changes. Every Playwright run
builds the current checkout, launches its own server on an OS-selected port,
and shuts it down afterwards. Existing local servers are never reused.
New schedules contain no user-defined people, shift types, or groups. E2E tests
that require populated entities must seed them explicitly.

For deterministic checks of version-dependent UI, restart the dev server with
an explicit version, for example:

```sh
APP_VERSION_OVERRIDE=v0.0.0 bun run dev -- --port 3006
```

Leave `APP_VERSION_OVERRIDE` unset for normal Git-derived versions.

Persist the saving app version with Optimize and Export backend settings. Add
targeted migrations for known older app versions or legacy shapes, and preserve
unrecognized versioned settings until a migration is defined.

Send backend requests through the page's authorized fetch helper so the selected
backend's token is attached. Job events use `EventSource` with the backend's
`links.events` URL as given, which already carries a scoped stream token when the
backend authenticates. Treat a `/info` response without an `auth` descriptor as an
open backend so older servers keep working.

Keep commit bodies focused on behavior and rationale. Do not mention routine
test additions or regression coverage unless the test strategy itself is
material to the change.

Page-title help icons link to the matching Zensical page under `/docs`. Keep
the mapping in `src/constants/urls.ts` synchronized with `../zensical.toml`.

Protect transient in-memory user work with `useTabSwitchWarning` when changing
tabs would discard it. Add a `beforeunload` guard when reload or close also
destroys that state.

Experimental AI controls must follow backend `/capabilities` responses. The
backend remains authoritative for feature enablement and input limits.
Treat an absent AI auth descriptor as a legacy open backend. When auth is
required, send the AI token through the shared authorized-header helper on
every session request, including the fetch-based event stream. Store it only
when the user explicitly opts in to unencrypted device storage.
The AI page defaults to the hosted `/ai` path on the production API and calls
the selected backend directly. Production NGINX must strip the `/ai`
prefix and disable response buffering. Keep credentials scoped to their
endpoint and lock the endpoint after a conversation creates a session. A
self-hosted build may set another default with `NEXT_PUBLIC_AI_API_URL`. When a
capability-gated control is missing, inspect the capabilities request from the
exact browser origin. A loopback-only browser check can miss CORS failures.
Replayable AI session events use `Last-Event-ID`, so include it in backend CORS
preflight coverage. Keep object URLs for workbook downloads alive until the
download is replaced or the page unmounts.
AI operation state belongs to `ChatLifecycle`. Finish only the operation that
owns a callback and derive busy/Stop state from its phases. Scope stream callbacks
to their connection, and scope other async completions to their conversation.
Replayable events carry run identity and advance the cursor only after a complete
SSE frame. Test overlapping foreground completion and background replay explicitly.
Apply streamed assistant output from both streams through `applyAssistantEvent`
and keep only stream-specific ownership and terminal handling in the page. When
AI chat status text, activity rows, or stream handling change, also run
`e2e/experimental-ai-basic.spec.ts` and `e2e/experimental-ai-proposal.spec.ts`,
because the affected E2E runner cannot infer them from source changes.
For AI chat issues involving the deployed service, test the real browser UI
against `https://api-staging.nursescheduling.org/ai`. Run the local frontend,
select that URL in the AI server control, and use `AI_AUTH_TOKEN` from the
ignored `../docker/.env.staging` when available. Never print or persist the
token in test output or browser storage. Seed a small valid schedule for
optimizer flows, then follow the visible chat and session events through the
terminal response. Mocked component tests alone cannot verify this path.

To test specific source files from the repository root, run:

```sh
./scripts/test_frontend_affected.sh web-frontend/src/path/to/file.ts
```

## TypeScript And React Style
- Mark a file written entirely by an AI coding agent immediately after the license
  block, using `// This test is mostly AI generated.` in a test and
  `// This code is mostly AI generated.` in any other new file.
- Use `PascalCase` for component files and components.
- Prefix hooks with `use`.
- Follow the existing Next.js App Router and shared-code patterns under `src/`.
- ESLint uses `next/core-web-vitals` plus TypeScript rules from
  `eslint.config.mjs`.
- Every frontend test file (`*.test.ts` and `*.test.tsx`) must include the AGPL
  header documented in `../docs/agent-license-headers.md`.
