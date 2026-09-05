# Backend Deployment

This deployment scaffold publishes the FastAPI backend through Cloudflare
Tunnel for `api.nursescheduling.org`. Cloudflare terminates public HTTPS, while
`cloudflared` connects outbound from the VM to the API container.

## Cloudflare Tunnel

- Create a [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/).
- Add a public hostname for `api.nursescheduling.org`.
- Point the hostname service to `http://nginx:8080`. NGINX sends
  `/ai/*` to the AI service and all other paths to the optimization API.
- Copy `.env.example` to `.env`.
- Set `CLOUDFLARE_TUNNEL_TOKEN` in `.env` to the token from the dashboard.
- Set `API_AUTH_TOKEN` in `.env`. The deployment image requires it.
- Enable [Always Use HTTPS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/).
- (Optional) Add a WAF/rate limit rule for `POST /optimize`.
- Keep ports `80` and `443` closed on the VM unless another service needs them.

> We used Cloudflare Tunnel for ease of setup, but you can easily switch to NGINX and Certbot if you have a dedicated public IP and are comfortable exposing it to the internet.

## API Authentication

Compose deployments are internet-facing, so they authenticate by default.
`Dockerfile.api` and `Dockerfile.api.staging` set `API_AUTH_REQUIRED=true` in the
image, which makes an empty `API_AUTH_TOKEN` a startup failure:

```text
API_AUTH_REQUIRED is set, so API_AUTH_TOKEN must not be empty
```

Generate a token and put it in the environment file:

```sh
openssl rand -base64 32
```

Serving a Compose deployment with no authentication is possible but has to be
chosen, by setting `API_AUTH_REQUIRED=false` in `.env`. That overrides the value
baked into the image.

Running the server outside these images leaves `API_AUTH_REQUIRED` unset, so
local development stays unauthenticated with no extra configuration.

Use at least 16 characters. When `API_AUTH_REQUIRED=true`, the backend rejects a
shorter token. When it is `false`, a shorter token is accepted with a warning for
local testing. Requests present the token as a bearer credential:

```sh
curl -H "Authorization: Bearer ${API_AUTH_TOKEN}" https://api.nursescheduling.org/optimize/options
```

`GET /info` and `GET /ready` stay public so clients and deployment probes can
discover the deployment without credentials. `/info` reports
`"auth": {"required": true, "scheme": "bearer"}`, which the frontend uses to
prompt for a token before calling a protected route. Every other application
route, including `/` and all of `/optimize`, answers `401` with a
`WWW-Authenticate: Bearer` header when the token is missing or wrong. Tokens
are compared in constant time, and `401` responses are not reported to Sentry
because unauthenticated probes of a public URL are expected.

When authentication is configured, the generated `/openapi.json`, `/docs`, and
`/redoc` routes are disabled and return `404`.

Running the backend outside Compose leaves `API_AUTH_TOKEN` unset, so local
development stays unauthenticated and needs no frontend changes.

The diagnostic service reads `DIAGNOSTIC_AUTH_TOKEN`, which both compose files
set from `API_AUTH_TOKEN`.

The AI service in both backend Compose files applies the same secure default
with `AI_AUTH_REQUIRED=true`. Set `AI_AUTH_TOKEN` before starting Compose. To
deliberately serve without AI authentication, set
`AI_AUTH_REQUIRED=false` in `docker/.env` and leave `AI_AUTH_TOKEN` empty. Native
runs leave required mode disabled, although setting a token still enables bearer
authentication.

NGINX removes the `/ai` prefix before forwarding requests to this
service and disables response buffering for its streaming endpoints. Keep the
Cloudflare Tunnel hostname pointed at `http://nginx:8080`, not directly at
either application container.

## Sentry

The Docker deployment configures only the Python backend. Keep all backend
servers in one Sentry project so issues, releases, alerts, and performance data
stay aggregated. Use `SENTRY_ENVIRONMENT` to distinguish production and
staging. Sentry records the backend host name as `server_name`, so separate
backend machines remain filterable without creating a project for every
server.

Set the projects' public DSNs in the deployment environment file:

```dotenv
SENTRY_BACKEND_DSN=https://backend-public-key@organization.ingest.sentry.io/backend-project-id
SENTRY_ENVIRONMENT=production
```

Compose passes `SENTRY_BACKEND_DSN` to every Python service as `SENTRY_DSN`.
The API, usage reporter, and diagnostic share the project and environment while
remaining filterable through their `app` tags.
`SENTRY_AUTH_TOKEN` is not needed by the running backend because the SDK sends
events through the DSN. Do not add a frontend DSN or Sentry auth token to this
backend environment file. Configure them in the frontend build environment as
described in the [developer guide](../docs/content/developer-guide/index.md#sentry).

An unset DSN retains the repository's existing shared Sentry project. Running
outside Docker uses the `development` environment. Set `DISABLE_SENTRY=1` in
the deployment environment file to disable reporting for every Python service.

## Start

Run these commands from the `docker/` directory.

The production API image uses `Dockerfile.api` and clones the latest `dev`
branch from GitHub in a temporary build stage. The build records a clean
`git describe --tags --always --dirty` value in `.app-version`, then copies only
`core/` and that version file into the runtime image. Git metadata and the Git
binary are excluded from the final image.

```sh
cd docker
docker compose -f compose.backend.yml up -d --build
```

The API derives one deployment ID from its container and server-launch
identity and shares it across all Uvicorn workers. The one-shot public
diagnostic is opt-in and does not start with the normal deployment command.
The normal Compose startup also starts one experimental AI worker. Configure
the AI block in `.env` before running:

```sh
docker compose -f compose.backend.yml up -d --build
```

The same behavior applies to `compose.backend.memory.yml`.

For staging, create a separate ignored environment file and use a staging-only
Cloudflare Tunnel token:

```sh
cp .env.staging.example .env.staging
# Set CLOUDFLARE_TUNNEL_TOKEN, API_AUTH_TOKEN, and DIAGNOSTIC_TARGET_URL in .env.staging.
APP_VERSION="$(git -C .. describe --tags --always --dirty)" \
  docker compose --env-file .env.staging -f compose.backend.yml up -d --build
```

The staging environment selects `Dockerfile.api.staging`, which copies the
current repository's `core/` directory into the image instead of cloning
GitHub. The host derives the app version before the build, and the Dockerfile
writes it to `.app-version` in the image. Linked Git worktrees are supported
and `.git` stays out of the build context and final image. Staging also sets
`COMPOSE_PROJECT_NAME=nurse-scheduling-backend-staging`. This overrides the
default `nurse-scheduling-backend` project name and gives staging its own
containers, network, and `redis-data` volume. Production and staging can then
run side by side on the same host.

Always pass `--env-file .env.staging` for every staging command, including
`ps`, `logs`, and `down`. Without it, Docker Compose loads `.env` and targets
production by default.

```sh
docker compose --env-file .env.staging -f compose.backend.yml ps
docker compose --env-file .env.staging -f compose.backend.yml logs -f
docker compose --env-file .env.staging -f compose.backend.yml down
```

The default compose file starts Redis alongside the backend. The backend runs
with:

- `JOB_BACKEND=redis`
- `JOB_REDIS_URL=redis://redis:6379/0`
- `JOB_REDIS_KEY_PREFIX=nurse_scheduling:jobs:v0`
- `JOB_WORKER_LEASE_SECONDS=90` by default
- `JOB_MAX_EVENTS_PER_JOB=1000` by default
- `USAGE_METRICS_ENABLED=true`
- `USAGE_METRICS_RETENTION_DAYS=30` by default

The backend publishes its accepted run options at `GET /optimize/options`.
The frontend uses this response for solver choices, timeout limits,
running-job controls, and the prettify default. Configure the response with:

- `OPTIMIZE_SOLVERS`, a comma-separated allowlist of selectors from the
  [solver reference](https://nursescheduling.org/docs/solvers/)
- `OPTIMIZE_DEFAULT_SOLVER`
- `OPTIMIZE_MIN_TIMEOUT_SECONDS`
- `OPTIMIZE_DEFAULT_TIMEOUT_SECONDS`
- `OPTIMIZE_MAX_TIMEOUT_SECONDS`
- `OPTIMIZE_DEFAULT_PRETTIFY`

The safe default exposes only `ortools/cp-sat`. In an existing GPU-capable
backend environment, copy the GPU settings template and set its tunnel token:

```sh
cp .env.gpu.example .env
```

This exposes both main solvers and selects `pulp/cuopt` by default. The template
does not add GPU access or cuOpt to the included CPU-only Compose deployment.

The API refuses to start if any configured solver is unavailable or a default
falls outside its advertised choices or range.

A complete compute benchmark creates `claimed-performance.env`. Merge its
three `CLAIMED_PERFORMANCE_*` values into the deployment environment to publish
the self-claimed score and provenance at `GET /info`. All three values must be
set together. The frontend displays the claimed score when the backend is
selected.

The API container runs multiple Uvicorn workers. Each worker claims jobs
from Redis and runs at most one optimization job locally. Workers renew shared
presence leases while idle and running. A job is failed and its capacity is
released if its owning worker lease expires.

To run one backend worker with process-local memory and no Redis service, use
the pre-Redis deployment configuration:

```sh
docker compose -f compose.backend.memory.yml up -d --build
```

Use the same compose file name for later commands when running the memory
configuration.

Check the API through Cloudflare:

```sh
curl https://api.nursescheduling.org/ready
curl https://api.nursescheduling.org/info
curl -H "Authorization: Bearer ${API_AUTH_TOKEN}" \
  https://api.nursescheduling.org/optimize/options
```

Run the public healthcheck test:

```sh
./test_public_healthcheck.sh
```

Check the backend directly from the VM:

```sh
docker compose -f compose.backend.yml exec api curl -fsS http://127.0.0.1:8000/ready
```

Check Redis from the API container:

```sh
docker compose -f compose.backend.yml exec api redis-cli -u redis://redis:6379/0 ping
```

`/ready` is the minimal deployment probe. `/info` performs the same readiness
check and adds the app version, deployment ID, process instance ID, process
start time, job backend, opaque job store ID, and whether authentication is
required. Both responses disable caching and stay public. The frontend uses
`/info` so one request provides readiness, version, and authentication
information.

## Weekly Usage Reports

The Redis deployment collects minimal per-job telemetry. Collection is
enabled by Compose and disabled by default for direct development launches.
It records job and pseudonymous client IDs, solver, lifecycle timestamps and
state, queue and runtime durations, outcome, failure code, solver status,
termination reason, configured timeout, and download count. It does not record
scheduling input, filenames, IP addresses, or email addresses.

Buckets run from Sunday at 00:00 through the next Sunday at 00:00 in the host
machine timezone. Each event belongs to the week when it occurs, so a job
submitted on Saturday and completed on Sunday can contribute to two different
weekly buckets. The reporter retrieves only the selected seven-day bucket. The
API and reporter mount the host timezone files so their boundaries remain
consistent, including daylight-saving transitions. Reports contain one CSV row
per associated job. Fields that are not available for an ongoing job remain
empty. Reporting does not remove telemetry. Rows and weekly membership indexes
expire after the configured retention interval following the end of their
event week. The interval defaults to 30 days.
Values below nine days are rejected because they cannot cover a complete week
before its reporting deadline.
Set `USAGE_METRICS_ENABLED=false` in the Docker environment file to disable
collection for a self-hosted deployment.

The default deployment runs one weekly service that stores delivery status in
Redis and writes reports to its container log by default. On startup it catches
up on completed, unsent weeks still covered by telemetry retention. It then
sleeps until the next reporting deadline.

Get the API key from the Mailgun dashboard under **Send > Sending > Domain
settings > Sending keys**. If Mailgun reports that the sender domain does not
exist, verify its records under **Domain settings > DNS records**. Then
configure these values in `.env`:

```dotenv
USAGE_REPORT_TRANSPORT=mailgun
USAGE_REPORT_SUBJECT="Nurse Scheduling backend usage: {week_id}"
MAILGUN_API_KEY=key-example
MAILGUN_DOMAIN=mg.example.com
MAILGUN_FROM="Nurse Scheduling Reports <reports@mg.example.com>"
MAILGUN_TO=operator@example.com
```

The reporter warns when Mailgun settings are present while the transport is
still `stdout`. In `mailgun` mode, it warns and stops when required Mailgun
settings are missing.

Then start the normal deployment with the reporter:

```sh
docker compose -f compose.backend.yml up -d --build
```

The reporter delivers the completed week on Sunday at or shortly after 00:00 in
the host machine timezone. Set `USAGE_REPORT_LOCAL_HOUR` to another local hour
from 0 through 23. A Redis-backed guard leaves at least ten minutes between any
two delivery attempts, including catch-up reports, service restarts, and two
bounded retries during a weekly run. The scheduler also waits at least ten
minutes between runs as a safeguard against invalid deadline logic. Delivery
checkpoints prevent normal duplicate sends. A process failure or ambiguous
transport error after Mailgun accepts a message but before Redis records the
checkpoint can still cause a retry and duplicate delivery. `MAILGUN_API_URL`
accepts Mailgun's HTTPS US or EU v3 endpoint for regional delivery.

`USAGE_REPORT_SUBJECT` controls both the email subject and the first line of the
report body. It supports the optional `{week_id}` placeholder. Invalid or
multiline templates stop the reporter during startup.

Trigger completed unsent reports immediately, without waiting for Sunday:

```sh
docker compose -f compose.backend.yml run --rm \
  usage-reporter python -m nurse_scheduling.server.usage_report --once
```

The command exits with a nonzero status if any delivery fails.

To send the newest retained week immediately, including the current partial
week or one already checkpointed as sent, add `--force`:

```sh
docker compose -f compose.backend.yml run --rm \
  usage-reporter python -m nurse_scheduling.server.usage_report --once --force
```

The command regenerates the entire selected Sunday-to-Sunday bucket from
retained telemetry instead of sending only changes since the previous report.
For the current week, it includes data recorded so far without marking the week
complete, so the normal full report is still delivered after Sunday. Forced
sends bypass the shared delivery interval but retain the per-week lock. No
retained telemetry or a held lock is reported as an error with a nonzero exit
status. A failed forced resend preserves any previous successful delivery
checkpoint. `--force` is rejected without `--once`.

For a one-time local rendering, use the default `stdout` transport. This marks
the report as delivered, so use an isolated Redis namespace if it must still be
emailed later:

```sh
docker compose -f compose.backend.yml run --rm usage-reporter \
  python -m nurse_scheduling.server.usage_report --once
```

## Public Diagnostic

The diagnostic service uses the `diagnostic` Compose profile so normal backend
startup does not submit diagnostic jobs. Run it explicitly against the
configured public URL:

```sh
docker compose -f compose.backend.yml --profile diagnostic \
  run --rm --no-deps diagnostic
```

After starting the staging deployment, run the diagnostic against its
configured public URL with the staging environment:

```sh
docker compose --env-file .env.staging -f compose.backend.yml \
  --profile diagnostic run --rm --no-deps diagnostic
```

Run it directly from a repository checkout, outside Docker Compose, after
installing the core dependencies. From the repository root:

```sh
source core/.venv/bin/activate
cd core
python -m nurse_scheduling.server.diagnostic \
  --target-url https://api.nursescheduling.org \
  --report-dir ../docker/diagnostic-reports
```

The same `DIAGNOSTIC_*` environment variables configure direct runs. The
`--target-url`, `--scenario`, and `--report-dir` arguments override their
corresponding environment values.

Set `DIAGNOSTIC_TARGET_URL` in the environment file to select production,
staging, or another public backend. Relevant defaults are:

- `DIAGNOSTIC_INFO_SAMPLES=100`
- `DIAGNOSTIC_PARALLEL_REQUESTS=10`
- `DIAGNOSTIC_EXPECTED_CONCURRENCY=3` for the Redis deployment
- `DIAGNOSTIC_MAX_JOBS=128`
- `DIAGNOSTIC_QUEUE_STABLE_SECONDS=10`
- `DIAGNOSTIC_WORKFLOW_TIMEOUT_SECONDS=600`
- `DIAGNOSTIC_JOB_TIMEOUT_SECONDS=3600`

The workflow timeout bounds startup sampling, job submission, and queue
transition checks. Cleanup and individual solver jobs have separate bounds.

The diagnostic samples `/info` and job snapshots with bounded concurrency, then
merges those identities with the API process recorded when each job is accepted
and the actual runner recorded when it starts. It submits the real 87-person
scenario until five jobs remain queued and measures the peak number of its own
running jobs. It cancels the first running job and finishes the others using
their feasible results. Queued jobs are then finished in batches matching the
observed peak concurrency. Every submitted job has a one-hour solver timeout
and bounded cleanup.

The first successful response is printed immediately. The concluding summary
includes the observed job backend. The example timing values below only show
the output format and are not measured deployment performance:

```text
CONNECTED target=https://api.nursescheduling.org http_status=200 status=ready
PASS target=https://api.nursescheduling.org job_type=large-ward-with-87-people-2025-11 job_backend=redis versions=1 deployments=1 instances=3 runners=3 stores=1 maxRunning=3 queue=PASS cleanup=PASS duration=148.0s
TIMING readiness=0.2s info_sampling=1.5s info_analysis=0.0s queue_saturation=12.0s queue_transition=132.0s identity_analysis=0.1s cleanup=2.2s
```

Timestamped JSON reports are written to the project-scoped
`diagnostic-reports` named volume. The summary and findings appear first,
followed by phase durations, distinct sampled responses, and job identities
with occurrence counts, job transitions, request errors, and cleanup details.
Exit codes are `0` for pass, `1` for a definite failure, and `2` for an
inconclusive run. Copy reports to the host when needed:

```sh
mkdir -p diagnostic-reports
docker compose -f compose.backend.yml run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --volume "$(pwd)/diagnostic-reports:/export" \
  --entrypoint sh diagnostic -c 'cp -R /reports/. /export/'
```

The image prepares `/reports` for its normal non-root user, so the diagnostic
run needs no `user` override. The extraction command uses the host user only to
write the bind-mounted destination. The volume survives normal
`docker compose down`, but `down -v` removes it.

Different app versions, deployment IDs, job backends, or automatically derived
job store IDs behind one public URL are configuration failures. Redis stores
persist a UUID inside their database and key namespace. Memory stores use the
process instance ID. A cloned Redis snapshot can duplicate its UUID, so equal
IDs remain evidence rather than proof of sharing. Cross-worker job visibility
is the definitive shared-store check.

Results are observational. Cloudflare routing can repeatedly select one
instance, so discovered instances are a lower bound. Unrelated users can
consume capacity or alter timing and make a run inconclusive without proving a
code or deployment defect.

## Frontend

The frontend selects an available backend from its built-in candidate list at
page load.

When `JOB_BACKEND=redis`, optimization jobs, SSE events, YAML inputs,
and XLSX outputs are stored in Redis so status, event, and download requests can
be served by any backend worker.

The bundled Redis service retains an AOF and a less-frequent RDB fallback in the
`redis-data` volume. The AOF uses `appendfsync everysec`, which limits the usual
abrupt-failure exposure to approximately the latest second while adding disk
I/O for stored YAML, event streams, XLSX artifacts, and telemetry. A single RDB
rule creates a snapshot after six hours when at least one write has occurred,
so an RDB-only recovery can be up to six hours behind. Redis also receives a
one-minute Compose shutdown grace period so its final blocking RDB save can
finish during planned restarts. Normal `restart` and `down` operations retain
the named volume. `down -v` removes all persisted Redis data. Back up the volume
when recovery from host or volume loss is required.

This configuration assumes a new Redis volume. Do not switch an existing
RDB-only volume to this configuration without migrating or discarding its data.
