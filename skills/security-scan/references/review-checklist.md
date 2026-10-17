<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Security review checklist

Check each area against the code at `HEAD` and the Compose files. Record the
file and line that shows the control, or the reproduction when it is missing.

## Deployment and edge

- Compose publishes no API, AI, Redis, or PostgreSQL port. Internal tools such
  as pgAdmin bind to `127.0.0.1` only.
- The env file sets `API_AUTH_REQUIRED`, `AI_AUTH_REQUIRED`, and the cookie
  `Secure` flags as intended. Secret files stay ignored by Git.
- Third-party images use pinned tags. The `cloudflared` image holds the tunnel
  token.
- NGINX replaces `X-Forwarded-For` with `CF-Connecting-IP` and bounds request
  bodies and timeouts for each route.

## Authentication and ownership

- Every route except the documented public ones requires a bearer key. Keys are
  compared in constant time and never accepted in a URL.
- Event-stream tokens are scoped to one job and expire.
- Job and session IDs are random. AI session routes check the owner cookie,
  including when a session is restored from PostgreSQL.
- Generated API docs are hidden when keys are required.

## Browser access

- CORS allows credentials only for `nursescheduling.org` over HTTPS and
  loopback origins. Check the API and AI service separately.
- Cookies are `HttpOnly`. An owner cookie with `SameSite=None` is also `Secure`.

## Abuse and cost

- The global queue limit, the per-address limit for unauthenticated jobs, and
  the maximum solver timeout bound how long one client can hold the workers.
- AI limits bound sessions, runs, tool rounds, attachment counts and sizes, and
  optimizer runs per session. Provider calls cost money, so check who can
  trigger them.

## Input handling

- YAML uses safe loaders, and alias expansion and nesting depth are bounded
  before parsing builds data.
- Upload sizes are bounded before buffering. Attachment names cannot choose a
  sandbox path.
- Error responses do not echo request bodies or reveal tracebacks.

## Sandbox

- E2B sandboxes have outbound Internet access disabled and receive no keys,
  database credentials, or host paths.
- Sandbox output reaches the user only as a validated schedule proposal or a
  bounded download.

## Output

- Exported workbooks write user-controlled text as text. A value that starts
  with `=`, `+`, `-`, or `@` must not become a formula.
- Downloads use fixed or server-generated file names.
- Assistant Markdown drops raw HTML and unsafe link schemes.

## Privacy and reporting

- Stored client addresses are salted digests. Telemetry excludes addresses and
  schedule content as `PRIVACY.md` states.
- Suspicious requests are reported without changing the response a caller sees.

## Dependencies

- Audit the Python runtime set and the shipped frontend packages. Note when an
  advisory applies only to tooling or to server features a static export does
  not run.
