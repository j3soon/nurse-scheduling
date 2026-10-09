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
