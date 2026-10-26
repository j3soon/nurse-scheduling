<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Core

Core contains the scheduling engine, CLI, optimization backend, and AI service.
Each independent shell block below starts from the repository root unless the
text specifies another directory. In the development container, dependencies
are installed system-wide. Skip virtual environment creation there.

## CLI

The main solver paths are:

- `ortools/cp-sat`, labeled **OR-Tools | CP-SAT**, is the recommended CPU
  solver and the default.
- `pulp/cuopt`, labeled **PuLP | cuOpt**, is the experimental GPU solver. It
  requires the NVIDIA cuOpt runtime and a supported GPU.

See the [solver reference](https://dev.nursescheduling.org/docs/developer-guide/solvers/) for the
full experimental solver matrix, platform requirements, runtime capabilities,
and test coverage.

```sh
cd core
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies, including the optional solvers and test tooling
uv pip install -r requirements-optional.txt
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

Run tests:

```sh
cd core
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

## Web Backend

The commands below are tested on Linux only.

```sh
cd core/nurse_scheduling
# development mode
fastapi dev serve.py

cd ..
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

For multiple Uvicorn workers or multiple backend machines, use Redis-backed job state. Redis stores job metadata,
queued job IDs, YAML inputs, XLSX artifacts, and replayable optimization events. Each backend process still runs at
most one optimization job locally, so `--workers 3` allows up to three simultaneous jobs across those worker processes.

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

Without Docker, install and start Redis with your operating system package manager.

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

### Inspect Redis Data

The Compose deployment uses Redis database `0` and the key prefix
`nurse_scheduling:jobs:v0`. Open `redis-cli` from the Redis container:

```sh
cd docker
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

## Experimental AI Chat

The experimental chat answers questions about the schedule currently open in
the frontend. Arbitrary file attachments are copied into a disposable sandbox
for inspection. The chat runs as a separate backend process and sends the
schedule and model-visible inputs to an OpenAI-compatible
provider.

Create a local configuration file. The real `docker/.env` file is ignored by Git:

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

Open `http://localhost:3000/experimental-ai`, select **Change**, then select
**Use localhost**. The local AI backend listens on `http://localhost:8001`.
The page otherwise uses `https://api.nursescheduling.org/ai` by default. See the
[AI assistant backend guide](https://dev.nursescheduling.org/docs/developer-guide/ai-assistant/)
for container commands, configuration, security notes, and focused tests.

## AI operations

Run these examples from the repository root. Configure secrets in the ignored
`docker/.env` file. Deployment, storage, and security details remain in the
[AI architecture guide](https://dev.nursescheduling.org/docs/developer-guide/ai-assistant/).

### Run locally

Copy the shared secret-free template from the `docker/` directory:

```sh
cp docker/.env.example docker/.env
```

Review the AI assistant block in `docker/.env`. Set the provider URL, API key,
model, and other settings for your environment. For an authenticated service,
also set one or more AI keys. To serve locally without auth, explicitly set
`AI_AUTH_REQUIRED=false` and leave `AI_AUTH_TOKEN` and `AI_AUTH_TOKENS` empty.
Then start the service:

```sh
./scripts/start_ai_backend.sh
curl http://localhost:8001/health
```

The launcher reads `docker/.env` automatically. Set `AI_ENV_FILE` to load
another path. Port `8001` avoids the normal backend on `8000`. Use another port
for a local documentation server when both services run at the same time. The
documented local Zensical port is `8003`.

The frontend uses `https://api.nursescheduling.org/ai` by default. Its server
control can select `http://localhost:8001` or a custom URL, and locks that
selection after a conversation starts. Set `NEXT_PUBLIC_AI_API_URL` before
building the frontend to provide a different deployment default. Remembered
credentials are stored unencrypted per endpoint only when the user opts in.

### Evaluation

The assistant is evaluated against fixed cases with verifiable criteria. This is
evaluation, and is separate from the solver performance benchmark described in
the backend server guide.

`core/tests/ai_eval/cases/` holds the cases grouped by category, from questions
answerable from the prompt summary through schedule edits to requests that must
be refused. Each case states criteria over the schedule a run produces, so
grading does not depend on how the assistant reached it. Every run contacts the
configured provider, so this is a manual tool rather than part of CI.

The runner needs the same provider settings the service uses:

| Variable | Required | Purpose |
| --- | --- | --- |
| `AI_PROVIDER_BASE_URL` | Yes | OpenAI-compatible endpoint. |
| `AI_PROVIDER_API_KEY` | Conditional | Provider bearer token. Required unless `AI_PROVIDER_PROFILES` supplies keys. |
| `AI_PROVIDER_MODEL` | No | Defaults to `local-model`. |
| `AI_SANDBOX_BACKEND` | Yes | Use `e2b`. |
| `E2B_API_KEY` | Yes | E2B Cloud credential used by the trusted application. |
| `E2B_TEMPLATE` | No | Defaults to `nurse-scheduling-ai-sandbox`. |
| `AI_EVAL_ARTIFACT_ROOT` | No | Report root, `artifacts` by default. |

The launcher reads them from `docker/.env`, so the shortest form is:

```sh
./scripts/run_ai_eval.sh --case clarify-night-request-scope
./scripts/run_ai_eval.sh --category 01-reading
./scripts/run_ai_eval.sh --tuning         # default tuning set
./scripts/run_ai_eval.sh --full           # every case
```

An evaluation scope is required. `--tuning` selects cases tagged `difficult`
or `tuning`, keeping prompt tuning focused as the corpus grows. Pass `--full`
to run every case. Explicit `--case`, `--category`, or `--tag` selectors bypass
the tuning tag filter and cannot be combined with `--tuning` or `--full`.
Start with cases relevant to the changed behavior, including a contrasting
control when ambiguity or scope is involved. Use `--repeat 3` on that selected
set to assess reliability before a broad tuning or full run. A single selected
pass is only a smoke check, not evidence of an improvement.
Cases may use `user_turns` for a real multi-turn conversation and
`intermediate_answer_contains` to verify that earlier turns ask a required
question without producing a proposal.

The launcher checks provider authentication before provisioning any E2B
sandbox. Providers without a `/models` endpoint produce an inconclusive result
and continue.

To run it without the launcher, load the settings first:

```sh
set -a && . ./docker/.env && set +a
cd core && python -m tests.ai_eval.runner --category 01-reading
```

Select cases with `--case` and `--category`, both repeatable. The runner creates
and destroys one E2B sandbox per case, so start with selected cases before
running the complete evaluation.

Every run writes a report to its own directory under
`artifacts/ai-evals/<timestamp>/`, alongside the performance benchmark reports,
and prints the path when it finishes. `summary.md` holds the pass count, median
seconds, LLM inference time, provider HTTP attempt and retry counts, and the
aggregate sandbox timing per category. It also includes per-case tables for
every sandbox timing and suspension metric. `results.jsonl` holds one line per case, and
`cases/<id>.json` holds the whole run for one case: the prompt it was given,
its reasoning, every tool call with its arguments and result, the answer, the
proposed schedule, timing breakdown, and each criterion with its outcome. Pass `--output-dir` to
choose the directory, which must not already exist, or set
`AI_EVAL_ARTIFACT_ROOT` to move the root.

Each case also records tool batches, calls per model turn, calls per batch,
parallel execution, execution time per batch, and the number of batches
containing multiple calls. The summary lists batch counts beside sandbox pause
metrics so pause behavior can be checked at model-turn boundaries instead of
inferred from the total tool count.

To measure E2B read concurrency without provider or model variance, run:

```sh
./scripts/run_ai_read_benchmark.sh
```

The benchmark alternates repeated sequential and concurrent read batches in one
warm sandbox. It reports median and p95 latency plus the median speedup under
`artifacts/ai-read-benchmarks/`. Use `--runs`, `--calls`, and `--bytes` to change
the sample count, calls per batch, and file size.

Timing fields use wall-clock seconds. `end_to_end_seconds` covers the agent run.
`llm_inference_seconds` sums only time awaiting provider stream events.
`llm_turn_seconds` records that wait separately for each logical model turn.
`provider_requests` reports the underlying HTTP attempts, retries, retried
turns, and attempts per logical turn. A successful retry therefore remains
visible in both the case artifact and aggregate summary.
`sandbox.lifetime_seconds` covers the complete create-to-destroy lifecycle. Its
mutually exclusive components are provisioning, execution, pause transition,
warm waiting, suspended, resume wait, and teardown. Their sum equals the
sandbox lifetime. Resume wait is the blocking interval after work needs the
sandbox but before E2B has made it usable, and `max_resume_wait_seconds` exposes
the worst individual resume. The `sandbox.suspension` object reports pause and
resume counts. It also reports `pause_cancel_count` for an in-progress pause
cancelled when new sandbox work arrives. A pause cancelled before its E2B
request starts or during final cleanup is not included. LLM inference can
overlap warm waiting, pause transition, and suspended time by design.

After each sandbox operation, the E2B backend schedules an explicit warm-memory
pause. Immediate follow-up activity cancels a pause that has not started, so
hydration and other consecutive operations stay together. Otherwise the pause
transition can overlap model inference, and E2B auto-resumes the same sandbox
when the next operation arrives. The memory snapshot is retained because five
fresh disk-only resume trials took 5.95 to 12.62 seconds, with an 8.01-second
median. Commands, file operations, pause/resume transitions, and close share
one serialized lifecycle lock.

Pause is optional optimization work and has a five-second application deadline.
The longer background deadline does not delay foreground work because new
activity cancels an in-progress pause. A failed or timed-out pause is not
retried. Because a timeout cannot prove whether E2B accepted the request, the
next operation first uses the separately bounded, replay-safe auto-resume probe.
A later idle pause may still be attempted because the control-plane failure may
have been transient.

The E2B creation timeout is not the hard deadline. E2B 2.46.0 testing showed
that an `on_timeout=kill` deadline did not kill a manually paused sandbox. The
application-level maximum agent-turn deadline and explicit kill in `finally`
are therefore the authoritative hard deadline. A separate live check confirms
that after this explicit kill, E2B rejects resume with `SandboxNotFoundException`.

Each created sandbox carries non-secret application ownership and hard-deadline
metadata. A completed `kill` response confirms either that the sandbox was
killed or was already absent. If deletion cannot be confirmed within request
cleanup, the sandbox ID enters a background queue that retries with capped
exponential backoff. At application startup and every configured reaper
interval, a metadata-filtered scan covers both running and paused sandboxes and
queues overdue instances. This avoids a full-account scan and lets a restarted
process recover cleanup work after a crash. If the application remains down,
no in-process cleanup can run, so deployments requiring cleanup during a full
service outage should invoke the same reconciliation from an external job.
The AI service initializes the shared Sentry integration with the
`app=ai-backend` tag. An unconfirmed request cleanup is logged as a warning.
An overdue sandbox or three consecutive background deletion failures is logged
as an error. All later attempts remain visible as warning logs, and a successful
cleanup is logged as confirmation. Sentry log alerts can use these severities
and the structured sandbox cleanup fields to notify administrators without an
error event for every retry.
Even a successful foreground kill is checked again in the background after one
E2B control-request timeout. This settling period covers a late pause or resume
request that can otherwise make a sandbox reappear after the kill response.
Confirmation lists only application-owned running and paused sandboxes. A
still-present ID is killed again with capped exponential backoff.

Deployments can run the same metadata-filtered cleanup independently of the AI
service with:

```bash
cd core
python -m nurse_scheduling.ai.sandbox.reap
```

The command requires only `E2B_API_KEY`, performs one reconciliation and
deletion pass, and returns a nonzero status if listing fails or any deletion is
still unconfirmed. Schedule it periodically when overdue sandboxes must be
cleaned while the AI service is offline.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_AUTH_TOKEN` | Unset | Shared bearer token. Setting it protects every AI session route. Use at least 16 ASCII characters. |
| `AI_AUTH_TOKENS` | Unset | JSON object mapping administrative IDs to bearer keys. |
| `AI_AUTH_REQUIRED` | `false` (`true` in Docker) | Fail startup unless at least one key of 16 or more ASCII characters is configured. |
| `AI_PROVIDER_BASE_URL` | Required | OpenAI-compatible API base URL. |
| `AI_PROVIDER_API_KEY` | Required unless profiles are set | Provider bearer token. Never commit it. |
| `AI_PROVIDER_MODEL` | `local-model` | Default model sent to chat completions. |
| `AI_PROVIDER_PROFILES` | Unset | JSON mapping AI credential IDs to LiteLLM `api_key` and `default_model`. |
| `AI_HISTORY_POSTGRES_URL` | Unset | PostgreSQL connection string for session recovery and turn metadata. Compose sets its internal URL directly. |
| `AI_REQUEST_LOG_ENABLED` | `true` | Log a question preview for each incoming message, which records chat text. |
| `AI_PROVIDER_TIMEOUT_SECONDS` | `180` | Provider request timeout. |
| `AI_PROVIDER_MAX_ATTEMPTS` | `5` | Total attempts per provider turn for transient HTTP, timeout, connection, or interrupted-stream failures. Retries stop 120 seconds after the first failure. |
| `AI_PROVIDER_RETRY_BACKOFF_SECONDS` | `2` | Initial retry delay, doubled up to 8 seconds with jitter. Valid server retry headers take precedence, with a 60-second maximum. |
| `AI_OPTIMIZER_BASE_URL` | `http://localhost:8000` (`http://api:8000` in Docker Compose) | Optimizer API base URL. Use HTTPS for a credentialed remote endpoint. An unavailable API produces a tool error without disabling chat. |
| `AI_OPTIMIZER_AUTH_TOKEN` | Unset (defaults to `API_AUTH_TOKEN` in Docker Compose) | Server-side optimizer API bearer token. Set it explicitly when the API uses identified keys. |
| `AI_OPTIMIZER_POLL_INTERVAL_SECONDS` | `1` | Delay between background optimizer status checks. |
| `AI_OPTIMIZER_REQUEST_TIMEOUT_SECONDS` | `30` | Timeout for one optimizer API request or result download. |
| `AI_OPTIMIZER_DEFAULT_TIMEOUT_SECONDS` | `300` | Optimizer time limit sent when the assistant omits one. Docker Compose derives it from `OPTIMIZE_DEFAULT_TIMEOUT_SECONDS`. |
| `AI_OPTIMIZER_RESULT_CACHE_BYTES` | `256000000` | Maximum total optimizer workbook bytes retained by one AI process. Oldest results are evicted first. |
| `AI_SANDBOX_BACKEND` | Required | Sandbox provider. Currently `e2b`. |
| `E2B_API_KEY` | Required for E2B | E2B Cloud credential used only by the trusted application. |
| `E2B_TEMPLATE` | `nurse-scheduling-ai-sandbox` | Prebuilt E2B template alias. |
| `AI_SANDBOX_COMMAND_TIMEOUT_SECONDS` | `60` | Default and maximum deadline for one shell command. |
| `AI_SANDBOX_TURN_TIMEOUT_SECONDS` | `21600` | Six-hour agent run deadline, including paused time. The E2B VM has a one-hour active timeout that each auto-resume restarts, and the application pauses it between tool batches. The Compose NGINX proxy waits up to 21660 seconds between response bytes. |
| `AI_SANDBOX_CLEANUP_TIMEOUT_SECONDS` | `10` | Deadline for destroying a sandbox. |
| `AI_SANDBOX_MAX_ATTEMPTS` | `3` | Total attempts for replay-safe E2B requests. |
| `AI_SANDBOX_RETRY_BACKOFF_SECONDS` | `0.5` | Initial E2B retry delay, doubled after each failure. |
| `AI_SANDBOX_PAUSE_REQUEST_TIMEOUT_SECONDS` | `5` | Deadline for the cancellable background pause request. |
| `AI_SANDBOX_CONTROL_REQUEST_TIMEOUT_SECONDS` | `2` | Deadline for each foreground auto-resume attempt and the E2B request timeout for destruction. |
| `AI_SANDBOX_REAPER_INTERVAL_SECONDS` | `30` | Interval for reconciling overdue running or paused E2B sandboxes owned by this application. |
| `AI_BACKEND_PORT` | `8001` | Port used by the development launcher. |
| `AI_COOKIE_SECURE` | `0` in the launcher | Use `0` for local HTTP and `1` for public HTTPS. Secure deployments use `SameSite=None` so approved cross-site frontends can retain session ownership. |
| `AI_SESSION_TTL_SECONDS` | `2592000` | Idle session lifetime. Session activity renews it. |
| `AI_MAX_SESSIONS` | `1000` | Maximum process-local sessions. With PostgreSQL, a new or restored session unloads the least recently used idle session instead of getting HTTP 429. Its stored uploads, generated ZIPs, and optimizer files remain in PostgreSQL and load again on demand. A session stays loaded while a response, optimizer run, or recovery write is unfinished, and after a failed save until a later save succeeds. |
| `AI_MAX_SESSION_BYTES` | `1073741824` | Retained-byte budget across live sessions, including chat text, uploads, and generated downloads. It includes every active attachment and pending file write. New sessions, uploads, schedule updates, and queued steering that would exceed it get HTTP 429. A completed turn keeps its exchanges. Further input is refused while capacity is exhausted. Size the process above this budget plus the newest turn of each session. |
| `AI_COMPACTION_RESERVE_TOKENS` | `16384` | Output reserve used by Pi's automatic compaction threshold and summary budgets. |
| `AI_COMPACTION_KEEP_RECENT_TOKENS` | `20000` | Estimated recent context retained after compaction. |
| `AI_AGENT_MAX_PARALLEL_TOOLS` | `16` | Concurrent independent read-only tools. Mutating batches remain sequential. |
| `AI_MAX_CONCURRENT_REQUESTS` | `4` | Maximum simultaneous agent runs. Each run holds a slot until it ends, which can take up to `AI_SANDBOX_TURN_TIMEOUT_SECONDS`, and other runs wait. |
| `AI_MAX_ARCHIVE_BYTES` | `10000000000` | Maximum file bytes that PostgreSQL stores per session: uploads, generated ZIPs, and optimizer files, including removed files. Removal does not free this capacity. A full session refuses new uploads with HTTP 413 and does not keep new generated ZIPs or optimizer results. Without PostgreSQL, this limit does not apply. |

Defensive input, history, response, and tool-count bounds use code defaults.
Optional environment overrides are documented in the limits page and omitted
from the environment examples. Questions have no separate character limit.
JSON request bodies are bounded to 64 MiB before parsing. Command output streams
to a sandbox log. The model sees
the last 2,000 lines or 50 KiB and the full log path when truncated. Sandbox
disk capacity and command deadlines bound log capture. See the
[AI runtime limits and Pi comparison](https://github.com/j3soon/nurse-scheduling/blob/dev/docs/content/developer-guide/ai-limits.md).

Attachments are always enabled. Every upload is copied unchanged into the
disposable sandbox, where the agent can inspect it with Pi-compatible tools.

### Model and reasoning selection

The chat lists models through the authenticated AI `/models` route. The backend
uses the caller's LiteLLM key for discovery and completion requests. Without
profiles, all AI keys use `AI_PROVIDER_API_KEY`. To isolate provider access, set
`AI_PROVIDER_PROFILES` in the ignored Compose environment file:

```dotenv
AI_PROVIDER_PROFILES='{"institution-a":{"api_key":"sk-example-a","default_model":"fast"},"person-b":{"api_key":"sk-example-b","default_model":"deep"}}'
```

The IDs must match `AI_AUTH_TOKENS`. The legacy `AI_AUTH_TOKEN` uses `legacy`.
When profiles are set, a key without a profile is refused. Provider keys stay on
the server. Rotating a provider key does not change chat ownership. Configure
model access, budgets, and rate limits on the LiteLLM virtual keys.

The backend intersects LiteLLM `/models` with optional `/model/info` metadata.
It excludes models marked as non-chat or without function calling. Discovery
results are cached per AI credential for 60 seconds. The gateway still enforces
access on every completion. When the gateway does not advertise reasoning
choices, the chat hides the reasoning dropdown and uses the gateway default.
Add explicit supported choices to each LiteLLM deployment's `model_info`:

```yaml
model_info:
  chat_display_name: Deep model
  chat_reasoning_options:
    - id: off
      label: Off
      parameters:
        thinking: {type: disabled}
    - id: high
      label: High
      parameters:
        reasoning_effort: high
```

Use only parameters supported by that exact model and gateway version. A budget
preset can use `thinking: {type: enabled, budget_tokens: 8192}`. Off must use a
model's actual disable setting, such as `reasoning_effort: none`, when supported.
The example shows alternative mechanisms. It does not claim every model supports
both. The chat matches each advertised choice against the deployment’s configured
`litellm_params` and selects the unique matching choice automatically. When a
match exists, the dropdown contains only advertised choices. Otherwise, Provider
default omits reasoning parameters and preserves gateway defaults. Do not
configure the gateway to silently drop unsupported reasoning parameters.

For a compatible Qwen deployment on vLLM, an Off option can set
`"parameters":{"chat_template_kwargs":{"enable_thinking":false}}`. An On
option sets the same boolean to `true`. Test these parameters on the deployment.
A Qwen effort preset can also set `reasoning_effort` inside
`chat_template_kwargs`, alongside `enable_thinking: true`. The backend permits
only these chat-template fields, `thinking`, and top-level `reasoning_effort`
in reasoning presets.

Advertise these choices in the gateway’s `model_info.chat_reasoning_options`.
The authenticated LiteLLM model list controls model access.

Users can switch models and reasoning while an answer streams. Each session saves
its current choice. Authenticated session owners can read or change it through
GET or PUT `/sessions/{session_id}/model-selection`, using `{model, reasoning}`.
Session creation also accepts an optional `selection`. A message without an
explicit selection uses the session's current choice.
An explicit message selection overrides that turn without changing the session
choice, so a delayed request cannot overwrite a newer choice.

Each accepted turn freezes its settings for retries, tool follow-ups, and steering.
Changing the current choice affects later turns, including new optimizer reviews.
Queued optimizer reviews use the session choice when they start.
Locally queued messages use the choice current when they start a new turn.
Reloading restores the session choice. PostgreSQL recovery preserves it across
backend restarts. Model settings are separate from expanding returned reasoning
text. Smaller context windows remain subject to the provider's input limits. The
chat reports the selected model's context limit when available.

The agent automatically summarizes older conversation context before requests
approach that limit. It retains recent tool exchanges and native reasoning for
compatible models. Summaries preserve goals, constraints, decisions, pending
work, and file context. Current schedule and file status stay in each request.
Summary calls use the selected model and appear in provider cost estimates.
The transcript shows when summarization starts, succeeds, fails, or stops.
After a successful summary, the context meter uses the smaller estimated context
until the next model call reports usage. Failed summaries keep the original context.
The composer footer updates Context and Tokens during streamed reasoning and answer
text. Token estimates are replaced when the provider reports usage. Estimated cost
updates when provider cost figures arrive. Missing prices stay unavailable.
Completion requests cap output against the model's advertised output limit and
remaining context, with a fixed safety margin of 4,096 tokens. History summaries
request up to 80 percent of the output reserve. Split-turn prefix summaries
request up to 50 percent. Numeric reasoning budgets leave at
least 1,024 tokens for the answer within the same completion limit. The gateway's
supported parameters determine the token-limit field. A model must report a
positive context window before generation.
A confirmed context overflow permits one compact-and-retry attempt. PostgreSQL
recovery retains successful summaries across service restarts.

The chat sends its stable session UUID in the `x-session-id` header on each
completion request, including retries, tool follow-ups, compaction summaries,
and optimizer reviews. It keeps the UUID after restoring a saved session.
LiteLLM can use this header when `session_affinity` is enabled under
`router_settings.optional_pre_call_checks` to keep a conversation on one
deployment. The provider copy for each run keeps concurrent conversations
separate. HTTP attempt IDs remain independent for cost accounting.

### Provider cost estimates

Enable cost reporting in the LiteLLM gateway configuration:

```yaml
litellm_settings:
  include_cost_in_streaming_usage: true
```

Verify this setting on the pinned LiteLLM release and each configured model.
The chat uses `usage.cost` from streaming responses. It ignores initial HTTP
cost headers because a stream can start before the gateway knows its cost.
The gateway remains responsible for model pricing, cache rates, and provider
billing rules. A gateway-reported zero is recorded as zero. Positive costs below
$0.000001 remain reported costs and display as `<$0.000001`, including subnormal
float values returned by gateways. Configure prices for custom models so missing
gateway pricing does not appear free.

Each HTTP attempt has a stable local call ID and an optional LiteLLM call ID.
The chat includes retries, tool follow-ups, compaction summaries, and optimizer reviews in its totals.
It keeps input, output, cached input, and reasoning token counts when supplied.
Reasoning tokens are already included in output tokens and are not added again.
Costs use decimal USD arithmetic on the server. The UI shows a turn total,
expandable call details, and the conversation total.

Pending calls have no final estimate yet. Unavailable means the gateway did not
report a cost, which can happen after Stop, a timeout, or a lost stream. Both
states remain visible beside the sum of known costs. These estimates cover LLM
calls. They exclude sandbox and scheduling service charges.

With `AI_HISTORY_POSTGRES_URL`, provider call events are durable in the existing
session event journal. A new attempt is checkpointed before its completion
request starts. Recovery replaces records by call ID and rebuilds totals from
the saved records, even if the process stopped before saving the session outcome.
Unfinished calls without a reported cost become unavailable after restart. Raw call events remain in chat
exports and share the session's retention policy. Without PostgreSQL, costs last
for the process lifetime and the browser retains its displayed totals for reload.
A cost record that could not be saved produces a warning and the normal journal
writer retries it. A crash can still lose cost data that the gateway never
returned or that storage could not save. Use LiteLLM spend logs and call IDs to
reconcile those calls. The displayed estimate is not a provider invoice.

`AI_AUTH_TOKENS` uses a JSON object such as
`'{"institution-a":"first-key","person-b":"second-key"}'`. IDs may contain
letters, numbers, underscores, and hyphens. They appear in administrative
session logs, while clients send only the key and never receive the ID. Remove a
pair and restart the service to revoke it. The legacy and identified settings
may coexist during migration.

### Run in the development container

Build the existing all-in-one development image from the repository root:

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

### Troubleshoot local development

| Problem | What to check |
| --- | --- |
| Send fails immediately | Start the AI backend and request `http://localhost:8001/health`. |
| Provider unavailable | Check `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_API_KEY`, and provider availability. |
| An attachment is rejected | Check the configured file count, byte limit, and public reverse-proxy body limit. |
| An answer stops early | Retry it. Cancelled and failed turns retain the question and an interruption note in later model context. |

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

### Run with Docker Compose

Both backend Compose variants start the AI service by default. Configure the AI
assistant block in `docker/.env`, then run from the `docker/` directory:

```sh
docker compose -f compose.backend.yml up -d --build
```

Use `compose.backend.memory.yml` in the same command when running the
process-local optimization backend. The AI service itself remains process-local
in both variants and listens on port `8001` inside the Compose network.

### AI tests

Run deterministic affected checks before live evaluations:

```sh
./scripts/test_core_affected.sh --base origin/dev
./scripts/test_ai_postgres.sh --base origin/dev
./scripts/test_frontend_affected.sh --base origin/dev
./scripts/test_frontend_e2e_affected.sh \
  web-frontend/e2e/experimental-ai-basic.spec.ts \
  web-frontend/e2e/experimental-ai-schedule-changes.spec.ts
```

Use the PostgreSQL wrapper when persistence changes. Check that database cases
executed. For a smaller change, pass explicit affected test paths. The
[AI validation guide](https://github.com/j3soon/nurse-scheduling/blob/dev/skills/implement-change-series/references/ai-validation.md)
explains when selected live cases are needed. Frontend ownership changes need
browser checks. Model, tool, and context changes need selected live cases.

The opt-in long-chat regression uses the real session API, configured providers,
and a prebuilt E2B template. Run it from the repository root:

```sh
AI_ENV_FILE=docker/.env.staging ./scripts/test_ai_compaction_live.sh
```

It runs five scenarios, at most four concurrently: automatic compaction across
runs, repeated compaction, model switching, Stop during a real summary stream
followed by resume, and manual compaction. Explicit token settings force
compaction without filling the provider's full context window. Checks cover remembered constraints, complete
tool exchanges, reconnect replay, attempt costs, stable session IDs, and missing
temporary files in each fresh sandbox. The schedule must stay unchanged.
The cancellation case pauses after receiving a real summary fragment.

The command reads `docker/.env`, falling back to `docker/.env.staging`, unless
`AI_ENV_FILE` is set. `AI_COMPACTION_SWITCH_MODEL` selects the second model and
defaults to `azure/gpt-6-luna`. Both models must be available, distinct, and report
a context limit. The command checks this before starting paid scenarios.
Traces go to `artifacts/compaction-live/`, or
`AI_COMPACTION_LIVE_OUTPUT_DIR`. The check uses no production database, does not
rebuild the template, and remains skipped in ordinary pytest runs.

## Inspect recent AI prompts

From the repository root, list recent PostgreSQL-backed user prompts:

```sh
./scripts/recent_ai_prompts.sh
./scripts/recent_ai_prompts.sh --sessions 10 --prompts 3 --chars 160
```

The defaults are 15 sessions, five prompts per session, and 300 characters per
prompt. Sessions sort by their latest user prompt. Prompts sort newest first,
including steering messages. Automatic optimizer prompts and assistant text are
excluded. Each session shows its ID, UTC timestamps, and shown/total prompt
counts. Each prompt shows its timestamp, character count, run status, and saved
input/output token totals. Token totals cover the whole run, including context
and tool exchanges. Steering prompts in one run share those totals. `?` means
usage is unavailable.

The command uses `docker/.env` and `docker/compose.backend.yml` by default.
If `docker/.env` is missing, it falls back to `docker/.env.staging` and prints
a notice. It always prints the selected Compose environment file to stderr.
Set `AI_ENV_FILE` to select a file explicitly and disable fallback, or
`AI_COMPOSE_FILE` for another Compose variant.
Set `AI_HISTORY_POSTGRES_URL` for native access with the core Python dependencies.
It uses one read-only database snapshot and does not apply migrations or prune
expired rows. Previews are truncated in SQL and printed on one line. The command
reads only retained history, so deleted content cannot appear.

## Export saved AI chats

From the repository root, export one PostgreSQL-backed chat session:

```sh
./scripts/export_ai_chat.sh SESSION_UUID artifacts/chat.zip
```

The command reads PostgreSQL through the Docker Compose `ai` service. It uses
`docker/.env` by default. Set `AI_ENV_FILE` to use another Compose environment
file. Set `AI_HISTORY_POSTGRES_URL` to read a native database instead. Native
database access requires the core Python dependencies. Docker exports do not
require Python or frontend dependencies on the host.

The browser's **Export Chat** control and this command use the same Python ZIP
writer. Each ZIP contains `chat.html`, `chat.md`, `chat.json`, `schedule.yaml`,
`manifest.json`, and `attachments/`. It includes removed uploads, generated ZIPs,
and optimizer files. The manifest records file origins, removal times, sizes,
and hashes. HTML and Markdown link to the bundled files and display times in UTC.
HTML exports show excessively nested Markdown as escaped plain text.

Exports use one consistent database snapshot, including saved failed, stopped,
and unfinished runs. File reads are bounded to 1 MiB chunks and the ZIP is built
on disk. A failed command preserves its destination. The browser downloads
directly through a short-lived link rather than buffering the ZIP in JavaScript.
PostgreSQL history is required. All files expire with their session. Files lost
before the archive migrations cannot be recovered.
