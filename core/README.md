# Core

Core contains the CLI, the scheduling engine, the FastAPI optimization
backend, and the experimental AI assistant service.

- CLI entry point: `nurse_scheduling.cli`
- Backend ASGI entry point: `nurse_scheduling.serve:app`
  (`nurse_scheduling/serve.py`)
- AI service ASGI entry point: `nurse_scheduling.ai_serve:app`

## Install

Run commands from `core/`:

```sh
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies, including the optional solvers and test tooling
uv pip install -r requirements-optional.txt
```

`requirements.txt` holds only what the CLI and the backend need at runtime,
which keeps the deployment image small. `requirements-optional.txt` adds the
experimental solver backends and the test and lint tooling.

## CLI

The main solver paths are:

- `ortools/cp-sat`, labeled **OR-Tools | CP-SAT**, is the recommended CPU
  solver and the default.
- `pulp/cuopt`, labeled **PuLP | cuOpt**, is the experimental GPU solver. It
  requires the NVIDIA cuOpt runtime and a supported GPU.

See the [solver reference](https://nursescheduling.org/docs/solvers/) for the
full experimental solver matrix, platform requirements, runtime capabilities,
and test coverage.

```sh
cd core
# run the CPU solver, OR-Tools | CP-SAT is the default
python -m nurse_scheduling.cli <input_file_path> [output_csv_path] --solver ortools/cp-sat
# for example:
python -m nurse_scheduling.cli tests/testcases/basics/01_1nurse_1shift_1day.yaml
# run the GPU solver, PuLP | cuOpt
python -m nurse_scheduling.cli <input_file_path> [output_csv_path] --solver pulp/cuopt
# run CLI with prettify and verbose
python -m nurse_scheduling.cli <input_file_path> [output_xlsx_path] --verbose --prettify
# record solver progress as JSON Lines for later plotting
python -m nurse_scheduling.cli tests/testcases/real/large-ward-with-87-people-2025-11.yaml --verbose --prettify --timeout 180 --progress-output progress.jsonl
```

## Web backend

Start the development server from the repository root:

```sh
./scripts/start_backend.sh
```

or run FastAPI directly in development mode:

```sh
cd core/nurse_scheduling
fastapi dev serve.py
```

Verify the process and its dependencies:

```sh
export API_URL="${API_URL:-http://localhost:8000}"

curl "$API_URL/ready"
curl "$API_URL/info"
```

`/ready` returns a minimal readiness result. `/info` also includes the API and
application versions plus current worker status and activities.

Interactive OpenAPI documentation is available at `$API_URL/docs`, with the
schema at `$API_URL/openapi.json`.

Run the serve checks from `core/`:

```sh
# run curl (needs to be run after the server is running)
./tests/test_serve_curl.sh
# run serve tests (don't need to be run after the server is running)
python tests/test_serve.py
# or
pytest tests/test_serve.py --log-cli-level=INFO
```

By default, the server exposes only **OR-Tools | CP-SAT** and keeps job state
in process-local memory:

```sh
cd core
JOB_BACKEND=memory \
OPTIMIZE_SOLVERS=ortools/cp-sat \
OPTIMIZE_DEFAULT_SOLVER=ortools/cp-sat \
uvicorn nurse_scheduling.serve:app --no-access-log
```

To expose a GPU-only **PuLP | cuOpt** server, run this command in the cuOpt
environment or GPU development container:

```sh
cd core
JOB_BACKEND=memory \
OPTIMIZE_SOLVERS=pulp/cuopt \
OPTIMIZE_DEFAULT_SOLVER=pulp/cuopt \
uvicorn nurse_scheduling.serve:app --no-access-log
```

For multiple Uvicorn workers or multiple backend machines, use Redis-backed job
state. Redis stores job metadata, queued job IDs, YAML inputs, XLSX artifacts,
and replayable optimization events. Each backend process still runs at most one
optimization job locally, so `--workers 3` allows up to three simultaneous jobs
across those worker processes.

```sh
cd core
JOB_BACKEND=redis \
JOB_REDIS_URL=redis://localhost:6379/0 \
JOB_REDIS_KEY_PREFIX=nurse_scheduling:jobs:v0 \
uvicorn nurse_scheduling.serve:app --workers 3 --no-access-log
```

The optional `JOB_WORKER_LEASE_SECONDS` setting defaults to 90 seconds. Keep it
long enough to tolerate brief Redis interruptions. Every worker renews its
presence lease every third of that interval, including while idle.

Replayable event history is capped at 1,000 events per job. Set
`JOB_MAX_EVENTS_PER_JOB` to choose a different positive limit.

The backend is the source of truth for the optimization controls shown by the
frontend. `GET /optimize/options` returns the allowed solvers, integer timeout
range, running-job controls, and prettify default. Configure them with:

```sh
export OPTIMIZE_SOLVERS=ortools/cp-sat,pulp/cuopt
export OPTIMIZE_DEFAULT_SOLVER=ortools/cp-sat
export OPTIMIZE_MIN_TIMEOUT_SECONDS=1
export OPTIMIZE_DEFAULT_TIMEOUT_SECONDS=300
export OPTIMIZE_MAX_TIMEOUT_SECONDS=3600
export OPTIMIZE_DEFAULT_PRETTIFY=true
```

The server is unauthenticated by default, which suits local development. Set
the legacy `API_AUTH_TOKEN` or a JSON object such as
`API_AUTH_TOKENS='{"institution-a":"key"}'` to require a bearer key on every
application route except `/info` and `/ready`:

```sh
cd core
API_AUTH_TOKEN="$(openssl rand -base64 32)" \
uvicorn nurse_scheduling.serve:app --no-access-log
```

`GET /info` reports `auth.required` so the frontend can prompt for a key.
The generated `/openapi.json`, `/docs`, and `/redoc` routes are disabled while
authentication is configured.
The images under `docker/` set `API_AUTH_REQUIRED=true`, so a deployed backend
refuses to start without a configured key. Serving one without authentication
requires `API_AUTH_REQUIRED=false`.

Only advertise solvers available on that machine. The server validates the
configured runtimes at startup.

### Redis

Without Docker, install and start Redis with your operating system package
manager.

Ubuntu/Debian:

```sh
sudo apt-get update
sudo apt-get install redis-server
redis-server --daemonize yes
redis-cli ping
```

macOS with Homebrew:

```sh
brew install redis
brew services start redis
redis-cli ping
```

Run the Redis backend tests against a local Redis database:

```sh
cd core
JOB_REDIS_TEST_URL=redis://localhost:6379/15 pytest --log-cli-level=INFO tests/test_optimize_job_backends.py
```

For Docker Compose deployment, `docker/compose.backend.yml` starts a Redis
service and configures the backend to use it:

```sh
cd docker
docker compose -f compose.backend.yml up -d --build
```

#### Inspect Redis Data

The Compose deployment uses Redis database `0` and the key prefix
`nurse_scheduling:jobs:v0`. Open `redis-cli` from the Redis container:

```sh
docker compose -f compose.backend.yml exec redis redis-cli -n 0
```

Useful inspection commands include:

```text
DBSIZE
SCAN 0 MATCH nurse_scheduling:jobs:v0:* COUNT 100
ZRANGE nurse_scheduling:jobs:v0:jobs 0 -1 WITHSCORES
ZRANGE nurse_scheduling:jobs:v0:queue 0 -1 WITHSCORES
SMEMBERS nurse_scheduling:jobs:v0:pending
ZRANGE nurse_scheduling:jobs:v0:workers:leases 0 -1 WITHSCORES
HGETALL nurse_scheduling:jobs:v0:workers:tokens
HGETALL nurse_scheduling:jobs:v0:workers:active
GET nurse_scheduling:jobs:v0:job:<job-id>
GET nurse_scheduling:jobs:v0:job:<job-id>:input
XRANGE nurse_scheduling:jobs:v0:job:<job-id>:events - + COUNT 20
HGETALL nurse_scheduling:jobs:v0:job:<job-id>:artifact_metadata
```

Use `SCAN` instead of `KEYS *` on a busy database. Job artifacts are binary and
are better inspected through the API download endpoint.

To run one backend worker with process-local memory and no Redis service, use
the pre-Redis deployment configuration:

```sh
cd docker
docker compose -f compose.backend.memory.yml up -d --build
```

The bundled Redis service persists an AOF with `appendfsync everysec` and keeps
an RDB fallback after six hours when at least one write has occurred. This
limits the usual abrupt-failure exposure to approximately the latest second,
while an RDB-only recovery can be up to six hours behind. Redis installed
outside the bundled Compose deployment keeps its system persistence policy.

## Backend configuration

All server settings are read once when the application is constructed.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `JOB_BACKEND` | `memory` | Select `memory` or `redis` storage. |
| `JOB_REDIS_URL` | `redis://localhost:6379/0` | Set the Redis connection URL. |
| `JOB_REDIS_KEY_PREFIX` | `nurse_scheduling:jobs:v0` | Namespace and schema version for Redis keys. |
| `JOB_MAX_PENDING` | `32` | Limit queued, running, and cancelling jobs. |
| `JOB_MAX_RETAINED` | `128` | Limit all retained jobs, including terminal jobs. |
| `JOB_RETENTION_SECONDS` | `86400` | Retain terminal jobs for this duration. |
| `JOB_MAX_EVENTS_PER_JOB` | `1000` | Limit replayable events retained per job. |
| `JOB_CLAIM_POLL_SECONDS` | `1` | Set the delay between attempts to claim work. |
| `JOB_WORKER_LEASE_SECONDS` | `90` | Set how long a worker remains online without renewal. |
| `JOB_MAINTENANCE_INTERVAL_SECONDS` | `30` | Set the delay between maintenance passes. |
| `JOB_SSE_KEEPALIVE_SECONDS` | `10` | Set the maximum SSE wait before a keepalive. |
| `OPTIMIZE_MAX_YAML_BYTES` | `2097152` | Limit the submitted YAML size. |
| `OPTIMIZE_SOLVERS` | `ortools/cp-sat` | Set the ordered comma-separated solver allowlist. |
| `OPTIMIZE_DEFAULT_SOLVER` | `ortools/cp-sat` | Set the solver used when a request omits one. |
| `OPTIMIZE_MIN_TIMEOUT_SECONDS` | `1` | Set the smallest accepted timeout. |
| `OPTIMIZE_DEFAULT_TIMEOUT_SECONDS` | `300` | Set the timeout used when a request omits one. |
| `OPTIMIZE_MAX_TIMEOUT_SECONDS` | `3600` | Limit the timeout accepted from a request. |
| `OPTIMIZE_DEFAULT_PRETTIFY` | `true` | Set prettification when a request omits one. |
| `OPTIMIZE_TIMEOUT_GRACE_SECONDS` | `90` | Set the process grace added to the requested timeout before forced termination. |
| `CLAIMED_PERFORMANCE_SCORE` | unset | Publish the server's self-claimed normalized performance score. |
| `CLAIMED_PERFORMANCE_APP_VERSION` | unset | Record the app version used for the claimed-performance benchmark. |
| `CLAIMED_PERFORMANCE_MEASURED_AT` | unset | Record the benchmark report time as an ISO 8601 date and time with a timezone. |
| `API_AUTH_TOKEN` | unset | Require this shared bearer token on every application route except `/info` and `/ready`. |
| `API_AUTH_TOKENS` | unset | Require one of the bearer keys in this JSON object mapping administrative IDs to keys. |
| `API_AUTH_REQUIRED` | `false` | Require authentication, making an empty legacy and identified key set a startup failure. Set in the deployment images. |
| `DISABLE_SENTRY` | unset | Disable error reporting for all Python services when set to a non-empty value. |
| `SENTRY_DSN` | shared development project | Select the Python services' shared Sentry project DSN. Docker maps this from `SENTRY_BACKEND_DSN`. |
| `SENTRY_ENVIRONMENT` | `development` | Set the Sentry environment for all Python services. The `app` tag separates backend, usage reporter, and diagnostic events. |
| `SENTRY_RELEASE` | derived from the app version | Override the release reported to Sentry. |

Numeric values must be positive. `JOB_MAX_RETAINED` must be at least
`JOB_MAX_PENDING`. The default solver must be advertised, and the timeout
default must remain within the configured minimum and maximum.

Both key settings are optional and unset by default, so a locally run server
needs no credentials. Setting either one turns on authentication for that
deployment. Use at least 16 characters per key. When
`API_AUTH_REQUIRED=true`, the backend rejects a shorter key. When it is
`false`, a shorter key is accepted with a warning for local testing.

The three `CLAIMED_PERFORMANCE_*` values are optional, but they must be set
together. A complete compute benchmark writes them to
`claimed-performance.env` beside its report. The API publishes the result at
`GET /info` as `claimed_performance`. The frontend displays it as
`Claimed performance` when that backend is selected.

Deployment values are set in the ignored `docker/.env` file. The tracked
`docker/.env.example` documents the deployment subset and is the source of
truth for it.

## AI backend

The experimental chat answers questions about the schedule currently open in
the frontend. Arbitrary file attachments are copied into a disposable sandbox
for inspection. The chat runs as a separate backend process and sends the
schedule and model-visible inputs to an OpenAI-compatible
provider.

### Local

Create a local configuration file. The real `docker/.env` file is ignored by
Git:

```sh
cp docker/.env.example docker/.env
# Review and update the AI values. Set AI_AUTH_REQUIRED=false and leave
# AI_AUTH_TOKEN and AI_AUTH_TOKENS empty only for intentional local no-auth use.
```

Start the AI backend and frontend in separate terminals:

```sh
./scripts/start_ai_backend.sh
./scripts/start_frontend.sh --hostname 0.0.0.0
```

The launcher reads `docker/.env` automatically. Set `AI_ENV_FILE` to load
another path. Port `8001` avoids the normal backend on `8000`. Use another port
for a local documentation server when both services run at the same time. The
documented local Zensical port is `8003`.

Verify the service:

```sh
curl http://localhost:8001/health
```

Open `http://localhost:3000/experimental-ai`, select **Change**, then select
**Use localhost**. The local AI backend listens on `http://localhost:8001`.
The page otherwise uses `https://api.nursescheduling.org/ai` by default. The
frontend server control can select `http://localhost:8001` or a custom URL and
locks that selection after a conversation starts.

### Development container

Build the existing all-in-one development image from the repository root and
pass the environment file:

```sh
docker build -f docker/Dockerfile.dev -t nurse-scheduling:dev .
docker run --rm -it \
  --name nurse-scheduling-dev \
  --network=host \
  --env-file docker/.env \
  -v "$(pwd):/app" \
  nurse-scheduling:dev
```

Start the AI backend inside the container:

```sh
./scripts/start_ai_backend.sh
```

Start the frontend from another host terminal:

```sh
docker exec -it -w /app nurse-scheduling-dev \
  ./scripts/start_frontend.sh --hostname 0.0.0.0
```

The optimizer tool is always available to the model. Native runs use
`http://localhost:8000` by default, while Docker Compose uses `http://api:8000`.
If that API is unavailable, the tool reports a request error and chat remains
available.

### Docker Compose

Both backend Compose variants start the AI service by default. Configure the AI
assistant block in `docker/.env`, then run from the `docker/` directory:

```sh
docker compose -f compose.backend.yml up -d --build
```

Use `compose.backend.memory.yml` in the same command when running the
process-local optimization backend. The AI service itself remains process-local
in both variants and listens on port `8001` inside the Compose network. Durable
chat logging, pgAdmin inspection, and deployment details are described in the
[AI assistant backend guide](https://nursescheduling.org/docs/ai-assistant/)
and the [deployment guide](https://nursescheduling.org/docs/developer-guide/reproduce/deploy/).

### AI backend configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_AUTH_TOKEN` | Unset | Shared bearer token. Setting it protects every AI session route. Use at least 16 ASCII characters. |
| `AI_AUTH_TOKENS` | Unset | JSON object mapping administrative IDs to bearer keys. |
| `AI_AUTH_REQUIRED` | `false` (`true` in Docker) | Fail startup unless at least one key of 16 or more ASCII characters is configured. |
| `AI_PROVIDER_BASE_URL` | Required | OpenAI-compatible API base URL. |
| `AI_PROVIDER_API_KEY` | Required | Provider bearer token. Never commit it. |
| `AI_PROVIDER_MODEL` | `local-model` | Model value sent to chat completions. |
| `AI_HISTORY_POSTGRES_URL` | Unset | PostgreSQL connection string for durable chat logging. Compose sets its internal URL directly. |
| `AI_HISTORY_RETENTION_DAYS` | `30` | Positive number of days to retain chat text and metadata. |
| `AI_REQUEST_LOG_ENABLED` | `true` | Log a question preview for each incoming message, which records chat text. |
| `AI_PROVIDER_TIMEOUT_SECONDS` | `180` | Provider request timeout. |
| `AI_PROVIDER_MAX_ATTEMPTS` | `3` | Total attempts for a provider request that times out before streaming begins. |
| `AI_PROVIDER_RETRY_BACKOFF_SECONDS` | `1` | Initial pre-stream timeout retry delay. The delay doubles after each failed attempt. |
| `AI_OPTIMIZER_BASE_URL` | `http://localhost:8000` (`http://api:8000` in Docker Compose) | Optimizer API base URL. Use HTTPS for a credentialed remote endpoint. An unavailable API produces a tool error without disabling chat. |
| `AI_OPTIMIZER_AUTH_TOKEN` | Unset (defaults to `API_AUTH_TOKEN` in Docker Compose) | Server-side optimizer API bearer token. Set it explicitly when the API uses identified keys. |
| `AI_OPTIMIZER_POLL_INTERVAL_SECONDS` | `1` | Delay between background optimizer status checks. |
| `AI_OPTIMIZER_REQUEST_TIMEOUT_SECONDS` | `30` | Timeout for one optimizer API request or result download. |
| `AI_OPTIMIZER_DEFAULT_TIMEOUT_SECONDS` | `300` | Optimizer time limit sent when the assistant omits one. Docker Compose derives it from `OPTIMIZE_DEFAULT_TIMEOUT_SECONDS`. |
| `AI_OPTIMIZER_MAX_RUNS_PER_SESSION` | `50` | Maximum background optimizer runs one chat session may start. |
| `AI_OPTIMIZER_MAX_RESULT_BYTES` | `10000000` | Maximum workbook bytes retained for one result download. |
| `AI_OPTIMIZER_RESULT_CACHE_BYTES` | `100000000` | Maximum total optimizer workbook bytes retained by one AI process. Oldest results are evicted first. |
| `AI_SANDBOX_BACKEND` | Required | Sandbox provider. Currently `e2b`. |
| `E2B_API_KEY` | Required for E2B | E2B Cloud credential used only by the trusted application. |
| `E2B_TEMPLATE` | `nurse-scheduling-ai-sandbox` | Prebuilt E2B template alias. |
| `AI_SANDBOX_COMMAND_TIMEOUT_SECONDS` | `30` | Default and maximum deadline for one shell command. |
| `AI_SANDBOX_TURN_TIMEOUT_SECONDS` | `3600` | Deadline for the complete sandbox-backed user message. |
| `AI_AGENT_MAX_TOOL_ROUNDS` | `200` | Maximum model tool-call rounds before the agent must answer from verified results. |
| `AI_AGENT_MAX_TOOL_CALLS` | `400` | Maximum total tool calls in one sandbox-backed user message. |
| `AI_SANDBOX_CLEANUP_TIMEOUT_SECONDS` | `10` | Deadline for destroying a sandbox. |
| `AI_SANDBOX_MAX_ATTEMPTS` | `3` | Total attempts for replay-safe E2B requests. |
| `AI_SANDBOX_RETRY_BACKOFF_SECONDS` | `0.5` | Initial E2B retry delay, doubled after each failure. |
| `AI_SANDBOX_PAUSE_REQUEST_TIMEOUT_SECONDS` | `5` | Deadline for the cancellable background pause request. |
| `AI_SANDBOX_CONTROL_REQUEST_TIMEOUT_SECONDS` | `2` | Deadline for each foreground auto-resume attempt and the E2B request timeout for destruction. |
| `AI_SANDBOX_REAPER_INTERVAL_SECONDS` | `30` | Interval for reconciling overdue running or paused E2B sandboxes owned by this application. |
| `AI_BACKEND_PORT` | `8001` | Port used by the development launcher. |
| `AI_COOKIE_SECURE` | `0` in the launcher | Use `0` for local HTTP and `1` for public HTTPS. Secure deployments use `SameSite=None` so approved cross-site frontends can retain session ownership. |
| `AI_SESSION_TTL_SECONDS` | `172800` | Idle session lifetime. Session activity renews it. |
| `AI_MAX_SESSIONS` | `1000` | Maximum process-local sessions. |
| `AI_MAX_HISTORY_MESSAGES` | `1000` | Conversation messages retained per session. |
| `AI_MAX_HISTORY_CHARS` | `200000` | Prompt budget for retained history. The newest messages that fit are sent, so a long session cannot outgrow the model context window. |
| `AI_MAX_MESSAGE_CHARS` | `8000` | Maximum question length. |
| `AI_MAX_SCHEDULE_BYTES` | `1000000` | Maximum UTF-8 YAML snapshot size. |
| `AI_MAX_CONCURRENT_REQUESTS` | `4` | Maximum simultaneous provider streams. |
| `AI_MAX_ATTACHMENT_FILES` | `8` | Maximum files attached to one question. |
| `AI_MAX_ATTACHMENT_BYTES` | `5000000` | Maximum bytes per attached file. |

Attachments are always enabled. Every upload is copied unchanged into the
disposable sandbox, where the agent can inspect it with Pi-compatible tools.

`AI_AUTH_TOKENS` uses a JSON object such as
`'{"institution-a":"first-key","person-b":"second-key"}'`. IDs may contain
letters, numbers, underscores, and hyphens. They appear in administrative
session logs, while clients send only the key and never receive the ID. Remove a
pair and restart the service to revoke it. The legacy and identified settings
may coexist during migration.

Deployment values are set in the ignored `docker/.env` file. The tracked
`docker/.env.example` documents the deployment subset and is the source of
truth for it.

### Troubleshoot the AI backend

| Problem | What to check |
| --- | --- |
| Send fails immediately | Start the AI backend and request `http://localhost:8001/health`. |
| Provider unavailable | Check `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_API_KEY`, and provider availability. |
| An attachment is rejected | Check the configured file count, byte limit, and public reverse-proxy body limit. |
| An answer stops early | Retry it. Cancelled and failed answers are not added to backend history. |

For a provider HTTP failure, search the AI backend log using the error ID shown
in the browser. If the logged response is a Cloudflare `520`, inspect the
provider origin for an empty, malformed, or abruptly closed response. A `525`
means Cloudflare could not complete TLS with the provider origin. Correlate the
logged timestamp and Cloudflare Ray ID with the provider proxy, tunnel, and
origin logs. See Cloudflare's [520](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-520/)
and [525](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-525/)
guidance.

#### Attachment capability discovery

The attachment control is available after capability discovery confirms the
server's file count and byte limits. If it is missing, compare the direct and
browser-facing responses:

```sh
curl http://127.0.0.1:8001/capabilities
curl https://api.nursescheduling.org/ai/capabilities
```

Use the endpoint shown by the frontend's AI server control for the
browser-facing check. If local capability discovery fails, check that port
`8001` is reachable and accepts the frontend origin. For production, check
`/ai/capabilities` through NGINX. When developing in a container, also
test the container address used by the browser. A loopback-only test can miss a
CORS failure or incomplete hydration.

## Tests

Run tests from `core/`:

```sh
# run the normal core test suite
pytest --log-cli-level=INFO
# run focused OR-Tools | CP-SAT tests
pytest --log-cli-level=INFO \
  tests/test_solver_ortools_cp_sat.py \
  tests/test_schedule_ortools_cp_sat.py
# run focused PuLP | cuOpt tests in the GPU environment
pytest --log-cli-level=INFO \
  tests/test_solver_pulp_cuopt.py \
  tests/test_schedule_pulp_cuopt.py
# run Python lint checks for core
ruff check nurse_scheduling tests
# auto-fix lint issues when possible
ruff check --fix nurse_scheduling tests
# apply consistent formatting
ruff format nurse_scheduling tests
```

Generate coverage report:

```sh
cd core
# terminal summary
pytest --cov=nurse_scheduling
# HTML report for local inspection
pytest --cov=nurse_scheduling --cov-report=html
# open report at:
# htmlcov/index.html
```

For more debugging output when a test fails:

```sh
cd core
pytest --log-cli-level=INFO tests/test_solver_ortools_cp_sat.py
pytest --log-cli-level=INFO tests/test_schedule_ortools_cp_sat.py
pytest --log-cli-level=INFO tests/test_solver_pulp_cuopt.py
pytest --log-cli-level=INFO tests/test_schedule_pulp_cuopt.py
```

Note that setting `WRITE_TO_CSV=True` in `core/tests/schedule_test_helper.py` is often useful for creating new test cases.

The checks under `core/tests/real/` intentionally omit pytest's `test_` filename prefix so they are not included in the
normal core suite. They solve larger real-world scenarios with fixed optimization budgets and run in the separate
`test-core-real.yaml` GitHub Actions workflow.

Note: The frontend now has Vitest coverage plus Playwright browser integration tests. The root GitHub Actions badge currently still points at the core workflow.

### Focused AI checks

Run the focused checks inside the development container:

```sh
cd /app/core
ruff check nurse_scheduling/ai nurse_scheduling/ai_serve.py \
  tests/test_ai_basic.py tests/test_ai_provider.py \
  tests/test_ai_sandbox.py tests/test_ai_sandbox_e2b.py \
  tests/test_ai_sandbox_agent.py tests/test_ai_pi_bash.py tests/test_ai_pi_edit.py \
  tests/test_ai_pi_read.py tests/test_ai_pi_write.py tests/test_ai_sandbox_tools.py \
  tests/test_ai_attachment_tools.py
pytest -q tests/test_ai_basic.py tests/test_ai_provider.py \
  tests/test_ai_sandbox.py tests/test_ai_sandbox_e2b.py \
  tests/test_ai_sandbox_agent.py tests/test_ai_pi_bash.py tests/test_ai_pi_edit.py \
  tests/test_ai_pi_read.py tests/test_ai_pi_write.py tests/test_ai_sandbox_tools.py \
  tests/test_ai_attachment_tools.py

cd /app/web-frontend
bun run test -- \
  src/app/experimental-ai/AssistantMarkdown.test.tsx \
  src/app/experimental-ai/aiClient.test.ts \
  src/app/experimental-ai/page.test.tsx \
  src/components/Navigation.test.tsx
bun run build
bun run test:e2e:affected -- e2e/experimental-ai-basic.spec.ts
```

### PostgreSQL chat history

Run PostgreSQL integration checks against a test database whose role can create
schemas. Each test creates and removes its own temporary schema:

```sh
cd core
AI_HISTORY_TEST_POSTGRES_URL=postgresql:///ai_history_test \
  .venv/bin/pytest -q tests/test_ai_history.py
```
