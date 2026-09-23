# Web Frontend

The web frontend is a Next.js app. The commands below are tested on Linux only.

Run commands from `web-frontend/`:

```sh
bun install
bun run dev
```

For building the static site:

```sh
cd web-frontend
bun run build
```

For linting:

```sh
cd web-frontend
bun run lint -- --fix
```

Run frontend unit/component tests:

```sh
cd web-frontend
bun run test
```

Run frontend coverage:

```sh
cd web-frontend
bun run test:coverage
```

Run frontend browser integration tests:

```sh
cd web-frontend
bunx playwright install-deps chromium
bunx playwright install chromium
bun run test:e2e
# or in interactive UI mode:
bun run test:e2e:ui
```

When using the repository `docker/Dockerfile.dev`, Chromium is preinstalled in the image at
build time using the frontend's locked Playwright version. If you rebuild the
image after Playwright version changes, `bun run test:e2e` and
`bun run test:e2e:ui` should not require rerunning `bunx playwright install chromium`
inside each new `docker run --rm` container.

In GitHub Actions, frontend browser integration tests run after frontend unit/coverage tests. The workflow uploads Playwright reports as build artifacts so failed CI runs keep browser traces and reports for debugging.

Generate a separate browser-flow coverage report from Playwright:

```sh
cd web-frontend
bun run test:e2e:coverage
bun run coverage:e2e:report
```

This writes a separate report under `web-frontend/coverage-e2e/` and does not replace the main Vitest coverage report under `web-frontend/coverage/`.

> `bun` can be replaced directly with `npm` for the basic Next.js workflow, but the documented project scripts assume Bun.

Local development needs no environment variables. Build-time `NEXT_PUBLIC_*`
variables (for example `NEXT_PUBLIC_AI_API_URL`, `NEXT_PUBLIC_DOCS_BASE_URL`,
and `NEXT_PUBLIC_SENTRY_DSN`) are set by the build provider. The Netlify build
environment is documented below.

## Hosting on Netlify

The root `netlify.toml` builds the static frontend into
`web-frontend/out` and publishes the documentation under `/docs`. After linking
the repository to a Netlify project, open **Project configuration → Environment
variables** and configure these variables with the **Builds** scope:

| Variable | Value | Sensitive |
| --- | --- | --- |
| `NEXT_PUBLIC_SENTRY_DSN` | Public DSN for the frontend Sentry project. | No |
| `SENTRY_ENVIRONMENT` | `production` for the production deploy context. Use a distinct value such as `staging` for branch deploys. | No |
| `SENTRY_PROJECT` | Slug of the frontend Sentry project. | No |
| `SENTRY_AUTH_TOKEN` | Sentry organization auth token allowed to create releases and upload source maps for the frontend project. | Yes |

Mark `SENTRY_AUTH_TOKEN` as **Contains secret values** in Netlify. Never prefix
it with `NEXT_PUBLIC_`, put it in `netlify.toml`, or commit it to an environment
file. The Next.js Sentry build plugin reads it only while building, then uploads
the release and source maps. Without it, the site still builds and browser
events still reach Sentry through `NEXT_PUBLIC_SENTRY_DSN`, but production stack
traces may remain minified.

To create the token:

1. Follow Sentry's [auth-token instructions](https://docs.sentry.io/account/auth-tokens/)
   to create an organization token through an internal integration.
2. Grant `org:ci` for release and source-map operations. Ensure the integration can access the
   team that owns `SENTRY_PROJECT`.
3. Copy the generated token into Netlify as `SENTRY_AUTH_TOKEN`, select the
   **Builds** scope, and mark it as **Contains secret values**.

Trigger a new deploy after changing any build environment variable. Configure
different `SENTRY_ENVIRONMENT` values per Netlify deploy context when production
and branch deploys share the same frontend Sentry project.
