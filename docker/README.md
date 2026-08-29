# Backend Deployment

This deployment scaffold publishes the FastAPI backend through Cloudflare
Tunnel for `api.nursescheduling.org`. Cloudflare terminates public HTTPS, while
`cloudflared` connects outbound from the VM to the API container.

## Cloudflare Tunnel

- Create a [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/).
- Add a public hostname for `api.nursescheduling.org`.
- Point the hostname service to `http://api:8000`.
- Copy `.env.example` to `.env`.
- Set `CLOUDFLARE_TUNNEL_TOKEN` in `.env` to the token from the dashboard.
- Enable [Always Use HTTPS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/).
- (Optional) Add a WAF/rate limit rule for `POST /optimize`.
- Keep ports `80` and `443` closed on the VM unless another service needs them.

> We used Cloudflare Tunnel for ease of setup, but you can easily switch to NGINX and Certbot if you have a dedicated public IP and are comfortable exposing it to the internet.

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

For staging, create a separate ignored environment file and use a staging-only
Cloudflare Tunnel token:

```sh
cp .env.staging.example .env.staging
# Set CLOUDFLARE_TUNNEL_TOKEN and DIAGNOSTIC_TARGET_URL in .env.staging.
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
start time, job backend, and opaque job store ID. Both responses disable
caching. The frontend uses `/info` so one request provides readiness and
version information.

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

The bundled Redis service uses the image's default RDB snapshot policy and the
`redis-data` volume. This is sufficient for multi-worker coordination, but an
abrupt Redis or host failure can lose writes since the latest snapshot. A
deployment that requires a smaller recovery-point window should enable Redis
AOF persistence or use a managed Redis service with an appropriate persistence
policy. AOF is not required for the backend's job-sharing behavior and adds
disk I/O for stored YAML, event streams, and XLSX artifacts.
