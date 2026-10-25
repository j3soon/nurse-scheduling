# Frontend Guidelines

The app uses the Next.js App Router. Shared code lives under `src/components/`,
`src/hooks/`, `src/utils/`, and `src/types/`.

## Commands
Check `test -f /.dockerenv` first, per the root `AGENTS.md` environment
section. In a dev container the checkout mounts at `/workspace/web-frontend`
and the toolchain comes preinstalled. On a host checkout, run from your
local `web-frontend/` clone and run `bun install --frozen-lockfile` before
the other commands.

- `bun install --frozen-lockfile`
- `bun run dev`
- `bun run build`
- `bun run lint -- --fix`
- `bun run test:affected`: reconcile dependencies, lint the full frontend, and
  run tests related to uncommitted `src/` changes with compact output. Shared
  config and deleted source files trigger the full unit/component suite. An
  unmatched source path fails instead of passing with zero tests.
- `bun run test`: run the full unit/component suite.
- `bun run test:e2e`: run Playwright integration tests.
- `bun run test:e2e:affected`: lint the full frontend and run changed or
  explicitly provided E2E specs with compact output on an isolated server.
  Stop after the first failure.

Use `bun run test:affected` for routine changes. Run the full unit/component
and browser suites when checking the full app or broad shared behavior.
After a large frontend change, such as a commit series or a change to shared
components, layout, or global CSS, run `bun run test:e2e:affected --full` once
before the branch is pushed. Changed-spec runs miss other specs that the change
breaks. CI stops at the first E2E failure, so each push can show only one of
them. The full suite takes about two minutes in the dev container. If you
cannot run it, tell the user that it was not run and that they can run it before
pushing.
Frontend unit/component tests use Vitest; browser integration tests use
Playwright. Keep test files and runner configuration outside the production
TypeScript project. Validate them with their respective test runners.

Prepare chat archives before starting a native download in a hidden frame. Keep
preparation and download errors on the chat page. Test both failure paths in
Chrome and Firefox. Keep large archives out of browser Blobs. Retain the frame
until the next export, conversation reset, or page unmount.

For row reorder tests, drop inside the intended half of the target row. Its
midpoint separates insertion before and after, so center drops are ambiguous.

For clipboard transformations, test a real browser paste and native text undo.
Preserve table cell separators and preformatted indentation. Use the clipboard's
plain text when the converter cannot preserve that structure.

Filesystem failure tests must accept the supported platforms' error codes.
Assert the failed operation and path as well as output preservation.

Give synchronous child processes in tests a timeout shorter than the test timeout.
The test runner cannot interrupt a blocked synchronous call.

Use Playwright locator actions for form controls. Before interacting with
statically rendered controls, wait for an observable result of client
initialization, such as loaded backend options enabling Optimize.

Treat transcript visibility preferences as display settings. Saved exports retain
reasoning, tool activity, model selections, and costs.

Keep assistant output and tool activity, including tool results, left-aligned.
Keep user, system, and app inputs to the model right-aligned with explicit role
labels. Show the generated conversation summary on the right as
`User · Conversation summary`. Keep display-only app events and notices in
separate centered bubbles. Compaction progress and outcomes are app notices.
Classify notices by their context provenance, because some report text supplied
to the model. A discarded summary belongs with app notices and must say that it
is omitted from future context. Derive these bubbles for display without changing
saved message identity, execution ownership, or model inputs. Match chat exports
to this convention.
Invalidate summaries across every reply from a failed run, including replies
before steering. Test foreground output, background replay, and reload.

When comparing chat exports with the live transcript, identify the same message
by its label or content. A foreground stream can prepend a system message after
the export snapshot, so message position is not stable.
Check saved transcript reconstruction against live message order as well as export
byte parity. Include steering before output and optimizer events between replies.

Both affected commands accept `--base REF` to include committed branch changes
since the merge base with `REF`, `--list` to inspect selection, and `--full` to
run their whole suite. `test:e2e:affected` passes its first undefined option
and every later argument to Playwright. For example,
`bun run test:e2e:affected e2e/experimental-ai-basic.spec.ts -g 'model'` runs
the matching tests of that spec. `test:e2e:affected` cannot infer browser
coverage from changed app source or public assets. Without explicit spec paths or `--full`,
it fails rather than silently skipping those changes. Every Playwright run
builds the current checkout, launches its own server on an OS-selected port,
and shuts it down afterwards. Existing local servers are never reused.
The full suite also starts a development server for the allowed-origin check.
If an existing server or development lock blocks it, test the current changes
in a separate checkout instead of stopping a user's server. For a temporary
`git worktree`, copy `web-frontend/node_modules` as hard links with `cp -al`.
Turbopack fails to build when `node_modules` is a symbolic link outside the
project root.

`next dev` can append a managed Next.js agent-rules block to this file. Browser
tests that launch a dev server can also cause this edit. After those checks,
inspect `git diff -- web-frontend/AGENTS.md` from the repository root. Review
generated guidance separately from intentional edits. If it is outside the
task scope, remove only the newly appended block after the dev server stops.
Preserve existing guidance and user changes.

New schedules contain no user-defined people, shift types, or groups. E2E tests
that require populated entities must seed them explicitly.

For responsive UI changes, check populated pages and open editing forms at phone
widths. Use touch device emulation for tap and reorder checks. Resizing a desktop
viewport alone does not exercise coarse-pointer controls or phone Enter behavior.
Check the visual viewport separately for fixed composers. Browser emulation does
not replace an iOS or Android keyboard check on a real device.
Text width depends on the system font. Chromium on the Ubuntu CI runner uses
DejaVu Sans, which is wider than phone, macOS, and Windows fonts. Size text that
must stay on one line so it fits in DejaVu Sans. Before you trust a local layout
result, check that `fc-match system-ui` reports DejaVu Sans.
Playwright `fullPage` screenshots under mobile emulation lose coarse-pointer
styles, so touch-only controls disappear from the image. For a full-height phone
screenshot, set the viewport height to the page height and take a normal capture.

E2E builds use the checkout's `git describe` version without `-dirty`. A build
from uncommitted changes otherwise shows a dirty-version warning on every YAML
upload, and upload specs that expect no dialog fail.

For deterministic checks of version-dependent UI, restart the dev server with
an explicit version, for example:

```sh
APP_VERSION_OVERRIDE=v0.0.0 bun run dev -- --port 3006
```

Leave `APP_VERSION_OVERRIDE` unset for normal Git-derived versions. Set it
explicitly when an E2E build must use another version.

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

Derive the AI context percentage and token count from the same backend token
value and model context limit. Label estimates. Keep character retention limits
out of the context percentage.

Experimental AI controls must follow backend `/capabilities` responses. The
backend remains authoritative for feature enablement and input limits.
Show the model lock that the backend saves for the session, and read it again
when a run starts or ends. Also lock the model control while a message is in
flight. A rejected message leaves it editable. Keep reasoning effort editable
during streaming for future runs. Enforce the same model lock on the backend. Save the session's
current choice separately from the active turn's accepted choice. Restore the
session choice after reload and serialize saves before submitting a new turn.
For retained attachments, count existing uploads toward session limits. Keep
per-file and session totals separate. Upload one file per request and preserve
confirmed uploads when a later upload fails.
AI operation state belongs to `ChatLifecycle`. Finish only the operation that
owns a completion, and derive busy and Stop state from its phases. Scope stream
callbacks to their connection and other async completions to their conversation.
Route session output by `run_id`, including events received before POST acceptance
is acknowledged. Buffer those events until acknowledgement identifies their run.
Keep accepted deferred events scoped to the conversation when their reader closes.
If a reset arrives before acceptance is acknowledged, request a covering snapshot
after the run is identified before deciding that its output expired. Preserve each
answer's original position when replacement replay rebuilds its output.
Replay snapshots replace output without completing unrelated active operations.
Keep queued messages waiting until foreground and background work are both idle.
AI chat does not require compatibility with older AI backend APIs. Update the
client and server together when their contract changes. When auth is
required, send the AI token through the shared authorized-header helper on
every session request, including the fetch-based event stream. Store it only
when the user explicitly opts in to unencrypted device storage.
The AI page defaults to the hosted `/ai` path on the production API and calls
the selected backend directly. Production NGINX must strip the `/ai`
prefix and disable response buffering. Read the AI service build version from
`/capabilities`. Fall back to the
parent `/info` endpoint when AI is mounted at `/ai` and capabilities omit
`app_version`. Send the frontend build version on session creation and every
chat message, including queued messages. Keep credentials scoped to their
endpoint and lock the
endpoint after a conversation creates a session. A self-hosted build may set another default with `NEXT_PUBLIC_AI_API_URL`. When a
capability-gated control is missing, inspect the capabilities request from the
exact browser origin. A loopback-only browser check can miss CORS failures.
Send the browser's IANA timezone on session creation, chat messages, and queued
messages. The backend sets the VM timezone once at creation. The agent gets the
current time with `date`. Preserve historical status messages in replay. New
requests use ordinary app events without an automatic status message.
Replayable AI session events use `Last-Event-ID`, so include it in backend CORS
preflight coverage. Keep object URLs for chat and workbook downloads alive until the
download is replaced or the page unmounts.

Use the shared `savedState` for AI input and Save and Load YAML. Omit automatically
generated export defaults from both, while preserving explicit empty or custom
layouts. Generate workbook defaults only at the optimizer submission boundary.

For reconnect tests, verify that the active HTTP stream actually closes. Browser
offline emulation alone can leave an existing stream open. Assert that reconnect
uses the same request ID and executes the accepted question only once. Mock
`/capabilities` with the real authentication and attachment-limit contract so
reload recovery follows the production path.
When adding AI session events, update the SSE decoder, chat hook callback dispatch,
assistant reducer, saved transcript projection, and exports together. Check the
visible browser result because decoder and reducer tests do not cover dispatch.
When you add an `ActivityEntry` kind, also accept it in `isActivityEntry` in
`chatConversation.ts`. Otherwise a reload discards the saved browser chat.

For session actions, check the action's full server event sequence through the
client decoder and transcript. Include `model_input`, not only `run_start`, text,
and `done`. Isolated server and UI mocks can both pass while their contracts differ.
Replay must replace existing messages in their original positions, including
optimizer input and steering replies. Capture the message ID before queuing React
state updates because one replay snapshot can contain several replies.
Use each event's `run_id` to identify replayed messages when `run_start` was trimmed.
Validate the whole SSE frame and every recovery entry before updating the cursor
or transcript. Acknowledge validated frames before consumer callbacks. Apply
replacement snapshots even when their IDs are at or below the stored cursor.
Browser timers have a maximum delay of about 24.8 days. Schedule longer session
expiry in bounded intervals and recheck the timestamp after each wake. Cover
both the intermediate wake and the final expiry with a clock-controlled test.

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
- Keep source filename stems distinct after lowercasing, including files with
  different extensions. On case-insensitive filesystems, a `.ts` helper can
  resolve before a `.tsx` component that shares its name.
- Prefix hooks with `use`.
- Follow the existing Next.js App Router and shared-code patterns under `src/`.
- Validate the whole CSV field before converting an integer count. `parseInt`
  accepts numeric prefixes of dates and malformed values, so it cannot validate
  those counts.
- ESLint uses `next/core-web-vitals` plus TypeScript rules from
  `eslint.config.mjs`.
- Every frontend test file (`*.test.ts` and `*.test.tsx`) must include the AGPL
  header documented in `../docs/agent-license-headers.md`.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
