---
name: screenshot-webpage
description: Capture deterministic PNG screenshots of local or authorized webpages with Playwright, including viewport, full-page or element capture, readiness checks, text assertions, light or dark color schemes, masking, and temporary element hiding. Use when Codex needs validated webpage screenshots for documentation, UI review, bug reports, or visual evidence.
---

# Screenshot Webpage

Use `scripts/capture-webpage.mjs` for repeatable captures. Validate the page
state before writing the image, then inspect the PNG rather than trusting the
command alone.

## Prepare the page

1. Start the application with its documented local command. Do not replace the
   user's running process or port without checking first.
2. Immediately before each capture, verify that the exact target URL responds.
   Repeat this preflight after restarting the application or changing its
   version. For example, use `curl --fail --silent --show-error URL >/dev/null`.
3. Use a stable local URL when available. Keep its hostname consistent across
   the dev server, preflight, and capture. Do not interchange `localhost` and
   `127.0.0.1`, because framework origin checks and application logic may treat
   them differently. Capture external or authenticated pages only when the user
   authorized access.
4. Use a module root with Playwright 1.51 or newer. A loopback capture allows
   loopback hosts by default. For any capture, list every non-loopback redirect,
   subresource, and WebSocket host with `--allow-host HOST`. For a remote
   capture, also list the page host and any loopback hosts. Link-local targets
   are always blocked.
5. Set up minimal test data and the exact UI state the documentation describes.
6. Identify visible text and a ready selector that prove the intended state.
7. Mask sensitive content with `--mask`. Never capture credentials, tokens, or
   unrelated personal data.

For a stateful client app, wait until imports or edits reach persistent storage
before navigating. After every navigation, assert page-specific hydrated data,
not only a server-rendered title. Use `--storage-state` when the target depends
on cookies, local storage, or session state prepared in another Playwright
flow. Playwright storage state preserves cookies and local storage, but not
session storage. The bundled script starts a fresh browser context when no
state file is provided.

## Capture the screenshot

Run the script from any directory:

```bash
node /path/to/screenshot-webpage/scripts/capture-webpage.mjs \
  http://127.0.0.1:3000/ /path/to/home.png \
  --module-root /path/to/project-with-node-modules \
  --storage-state /path/to/playwright-state.json \
  --viewport 1440x900 \
  --ready 'main' \
  --expect-text 'New Schedule' \
  --expect-text 'Continue'
```

Use `bun` instead of `node` when that is the repository standard. Use
`--selector` for one component or `--full-page` for the complete document.
Pass `--force` only after confirming that replacing the target image is
intended. Use `--executable-path` when the environment provides a browser
outside Playwright's managed browser directory.

When working in a repository, store final requested screenshots under its
top-level `artifacts/` directory unless the user specifies another location.
Keep exploratory captures there only while reviewing them, then remove those
temporary files.

For an authorized remote page, list the page host and every required asset host
explicitly:

```bash
node /path/to/screenshot-webpage/scripts/capture-webpage.mjs \
  https://docs.example.com/ /path/to/docs.png \
  --module-root /path/to/project-with-node-modules \
  --allow-host docs.example.com \
  --allow-host static.example.com
```

## Validate and document

1. Inspect the PNG with the available image viewer.
2. Confirm the intended controls are visible, text is legible, no dialog or
   tooltip obscures the page, and the crop has useful context.
3. Confirm the screenshot contains the seeded values, not starter data left by
   a persistence or hydration race.
4. Check a narrow viewport separately when documenting responsive behavior.
5. Verify the final documentation or page resolves the image without a 404.
6. Stop only local services started for the capture and remove temporary output.

Report the URL, viewport, captured state, and whether the image is a viewport,
full-page, or element screenshot.
