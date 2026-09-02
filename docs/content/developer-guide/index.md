# Developer Guide

Use these pages to develop, operate, or extend Nurse Scheduling.

- [Repository setup and development workflow](https://github.com/j3soon/nurse-scheduling#how-to-run)
- [Backend server](../backend-server.md)
- [Solver behavior](../solvers.md)
- [System design](../design.md)
- [Project timeline](../timeline.md)

For product use, start with the [User Guide](../user-guide/get-started.md).

For local page-help links, serve Zensical at `http://127.0.0.1:8001/docs/`.
Set `NEXT_PUBLIC_DOCS_BASE_URL` before starting the frontend when using another
documentation address. Production builds default to the same-origin `/docs`
path assembled by `netlify.toml`.

## Sentry

Development uses the repository's existing shared Sentry project by default.
For production, create separate frontend and backend Sentry projects. Keep
multiple servers for the same component in its project and distinguish
production from staging with environments.

Configure the static frontend in its build provider. For Netlify, follow the
[repository hosting instructions](https://github.com/j3soon/nurse-scheduling#hosting-on-netlify)
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
[backend deployment instructions](https://github.com/j3soon/nurse-scheduling/blob/dev/docker/README.md#sentry).
