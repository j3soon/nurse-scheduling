---
name: debug-backend-hangs
description: Diagnose backend HTTP requests that hang without a response in the Docker Compose services, including browser CORS-like errors, Cloudflare 524, and nginx 499 symptoms. Isolate the failing hop by bypassing each proxy layer, capture stuck-task stacks with faulthandler when py-spy is blocked, bind-mount patched source for fast instrumentation without image rebuilds, and bisect middleware and third-party integrations with minimal uvicorn processes inside the container. Do not use for CI failures, which skills/fix-github-ci covers, or for security review, which skills/security-scan covers.
---

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Debug Backend Hangs

A hanging request never answers, so every outer layer reports a different
misleading error. Work from the browser inward, prove which layer stops
answering, and instrument inside the container instead of reading logs from
outside.

## Read the symptoms

Symptoms that point at the same root cause, a request with no response:

- Browser devtools report `net::ERR_FAILED` or a CORS error about a missing
  `Access-Control-Allow-Origin` header. Any request that fails before the
  first response header looks like a CORS violation, including origin hangs.
  Check server logs before changing CORS configuration.
- Cloudflare returns 524 after about 100 seconds. The origin never sent
  response headers.
- nginx logs 499. The client gave up waiting.
- The FastAPI app logs an unhandled `starlette.requests.ClientDisconnect`
  while reading the body. This usually means the client vanished while the
  app was still waiting, not that the app failed first.
- Verify log line provenance before treating it as evidence. Shared loggers
  and startup builds can print lines that word-match the request path but
  come from a different system, such as an E2B template build printing
  upload messages.

## Isolate the failing hop

Bypass outer layers one at a time and find the innermost hop that still
fails. The endpoints differ per request, the method does not:

1. `docker exec` into the app container and `curl` the endpoint directly,
   for example `http://127.0.0.1:8001/...`. Compose containers hold
   `curl -s` and the service's own auth tokens from their environment.
2. Repeat through the in-stack nginx, then through the public tunnel URL.
   The first hop that differs from its inner neighbor owns the problem.
3. When the app itself hangs, rule out downstream sinks first: inspect
   `pg_stat_activity` and the container's `netstat` connections. A parked
   request with no open database connection is not waiting on the database.

## Instrument without rebuilding

Rebuilds are slow and the staged image copies the source tree at build time.
Iterate with bind mounts instead:

- Create an override file outside the repository, for example
  `/tmp/debug-override.yml`, and run
  `docker compose -f compose.backend.yml -f /tmp/debug-override.yml up -d ai`.
  Compose merges `command`, `environment`, and `volumes` onto the base
  service.
- Bind-mount a patched copy of one source file over its image path. Python
  reloads it on the next container recreate, with no image build.
- Add short `print("DBG: ...", flush=True)` markers that narrow the wait
  point to one call. Markers beat stack dumps for proving which line parks.
- Finish with `docker compose up -d ai` without the override to restore the
  stock command. Kill probe processes and remove probe files. Keep debug
    mounts out of commits.

## Capture stacks when py-spy is blocked

The stock containers reject `py-spy` because they lack `SYS_PTRACE` and the
host sets `kernel.yama.ptrace_scope=1`. Use in-process alternatives:

- Register `faulthandler` through the override command:

  ```yaml
  services:
    ai:
      command:
        - python
        - -c
        - |
          import faulthandler, signal, sys
          faulthandler.register(signal.SIGUSR1)
          from uvicorn.main import main
          sys.argv = ["uvicorn", "nurse_scheduling.ai_serve:app", "--host", "0.0.0.0", "--port", "8001"]
          main()
  ```

  Then `docker exec <container> kill -USR1 1` and read `docker logs`.
- A signal-raised dump shows thread frames. A request parked on `await`
  leaves the main thread inside the event loop, so also register a handler
  that walks `asyncio.all_tasks()` and prints each task's awaited frame.
- `faulthandler.dump_traceback_later(20, file=sys.stderr)` inside the
  patched code answers "is the stuck point before or after this line" while
  the request is otherwise silent.

## Bisect middleware and integrations

When a bare multipart parse works but the real handler hangs, run minimal
uvicorn processes on spare ports from inside the same container:

- Copy a tiny app to `/tmp` in the container. Start it with
  `docker exec -d <container> python /tmp/probe.py PORT` so the process
  inherits the container image and its installed package versions.
- Reuse the real route function and settings, then add one suspect layer at
  a time: each `app.add_middleware` entry, then each third-party `init()`.
- Treat `sentry_sdk.init()`, telemetry setup, and similar calls as request
  processing, not configuration. Their auto-enabled integrations wrap route
  handlers and can read `request.json()` or `request.form()` before the
  endpoint, which drains the body stream for any endpoint that re-reads it
  through a fresh `Request` wrapper. Disabling one integration at a time
  attributes the hang in minutes.
- Init flags are the cheapest bisect axis. Test the full option set, then
  the minimal init, then one option at a time before reading the vendor's
  source.
- Name probe files carefully. A scratch file named `bisect.py`, `random.py`,
  or any other stdlib module shadows the real module on `sys.path` and
  breaks unrelated imports in confusing ways. Clean its `__pycache__` too.

## Wrap up

- State which hop failed and the exact blocking call, not only the outer
  symptom.
- Recreate services with the unmodified compose files. Confirm the stock
  path still answers before starting the fix.
- Add a regression test at the layer that misbehaved. Unit tests for the
  integration init and the route mock are enough when the full stack
  induces the failure only under a third-party library.
