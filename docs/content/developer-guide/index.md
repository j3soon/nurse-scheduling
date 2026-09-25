# Developer Guide

Use these pages to develop, operate, or extend Nurse Scheduling.

## Reproduce

The setup and run pages are the repository READMEs, linked into the site so the
built documentation stays self-contained:

- [Setup and run](reproduce/setup.md): prerequisites, quick start, Windows, and the development container.
- [Core](reproduce/core.md): CLI, backend, AI backend, configuration, and tests.
- [Web frontend](reproduce/frontend.md): development, tests, builds, and Netlify hosting.
- [Documentation site](reproduce/docs.md): preview and build the documentation.

All deployed services read the gitignored `docker/.env` file. The tracked
`docker/.env.example` documents every deployment variable and is the source of
truth for it. Local development needs no environment variables.

## Backend Deployment

Publish the backend with Docker Compose and Cloudflare Tunnel. The
[backend deployment guide](backend-deployment.md) covers the tunnel, services,
environment, Sentry, usage reporting, and diagnostics.

## Architecture

- [Backend server](backend-server.md)
- [Backend containers and networks](containers.md)
- [Experimental AI assistant backend](ai-assistant.md)
- [Solver behavior](solvers.md)
- [Design rationale](design-rationale.md)

## Timeline

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
[frontend hosting instructions](reproduce/frontend.md#hosting-on-netlify)
for the exact variable table, UI location, scope, sensitivity settings,
token procedure, and missing-token behavior. Backend Docker deployments
configure `SENTRY_BACKEND_DSN` and `SENTRY_ENVIRONMENT` in the selected
`docker/.env` file. Follow the [deployment Sentry
instructions](backend-deployment.md#sentry).
