# Developer Guide

Use these pages to develop, operate, or extend Nurse Scheduling.

## Reproduce

These pages reuse the repository READMEs so commands have one source:

- [Setup and run](reproduce/setup.md): prerequisites and development containers.
- [Core](reproduce/core.md): CLI, optimization backend, AI service, and tests.
- [Web frontend](reproduce/frontend.md): development, browser tests, and Netlify.
- [Documentation](reproduce/docs.md): local preview and strict builds.

## Backend deployment

The [deployment guide](backend-deployment.md) covers Compose services,
authentication, storage, Sentry, usage reports, and diagnostics.

## Architecture

- [Backend server](backend-server.md)
- [Backend containers and networks](containers.md)
- [Experimental AI assistant backend](ai-assistant.md)
- [Solver behavior](solvers.md)
- [Design rationale](design-rationale.md)
- [Project timeline](../timeline.md)

For product use, start with the [User Guide](../user-guide/get-started.md).

For local page-help links, serve Zensical at `http://127.0.0.1:8003/docs/`.
Set `NEXT_PUBLIC_DOCS_BASE_URL` before starting the frontend when using another
documentation address. Production builds default to the same-origin `/docs`
path assembled by `netlify.toml`.

## Sentry

Development uses the repository's existing shared Sentry project by default.
For production, create separate frontend and backend Sentry projects. Keep
multiple servers for the same component in its project and distinguish
production from staging with environments.

Configure the static frontend in its build provider. For Netlify, follow the
[repository hosting instructions](reproduce/frontend.md#hosting-on-netlify)
for the exact UI location, scope, sensitivity settings, and missing-token
behavior:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_SENTRY_DSN` | Public DSN embedded in the browser build. |
| `SENTRY_ENVIRONMENT` | Environment embedded as `NEXT_PUBLIC_SENTRY_ENVIRONMENT`. |
| `SENTRY_PROJECT` | Frontend project slug used for source-map uploads. |
| `SENTRY_AUTH_TOKEN` | Secret build credential used for release and source-map uploads. |

`SENTRY_AUTH_TOKEN` is sensitive. Follow Sentry's
[auth-token instructions](https://docs.sentry.io/account/auth-tokens/) to create
an organization token through an internal integration. Grant `org:ci` and ensure the integration can access the team that owns the
frontend project. Store the token as a protected build-provider secret and do
not expose it with a `NEXT_PUBLIC_` prefix. The running frontend and backend SDKs
send events with their public DSNs and do not need this token.

Backend Docker deployments configure `SENTRY_BACKEND_DSN` and
`SENTRY_ENVIRONMENT` in the selected `docker/.env` file. See the
[backend deployment instructions](backend-deployment.md#sentry).
