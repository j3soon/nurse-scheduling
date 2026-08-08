# Nurse Scheduling System

[![tests](https://img.shields.io/github/actions/workflow/status/j3soon/nurse-scheduling/test-core.yaml?label=tests)](https://github.com/j3soon/nurse-scheduling/actions/workflows/test-core.yaml)
[![Netlify Status](https://api.netlify.com/api/v1/badges/8ec5c5da-89e1-41e5-87b3-133ce1007783/deploy-status)](https://nursescheduling.org/)
[![codecov](https://codecov.io/github/j3soon/nurse-scheduling/branch/dev/graph/badge.svg)](https://codecov.io/github/j3soon/nurse-scheduling)
[![docs](https://img.shields.io/badge/docs-pre--release-blue?logo=googledocs)](https://nursescheduling.org/docs/)

A flexible web application designed to streamline and automate nurse scheduling, suitable for a wide range of diverse and complex real-world requirements.

- Stable version (frontend-only) hosted on [Netlify](https://nursescheduling.org/).
- Development version hosted on [Netlify](https://dev.nursescheduling.org/).
- Documentation hosted on [Netlify](https://nursescheduling.org/docs/).
- Source code hosted on [GitHub](https://github.com/j3soon/nurse-scheduling).

## Introduction

The nurse scheduling (or employee scheduling) problem is a well-known problem in the field of operations research (OR) and can be (approximately) solved efficiently by constrained optimization.

However, constraints can differ greatly between hospitals and wards, and there is currently no unified framework for modeling these diverse requirements. Most existing literature focuses on modeling an over-simplified constraint set, which is not applicable to real-world situations. Therefore, in practice, the problem is still often solved by hand with the help of Excel, which is often extremely time-consuming. The entire process requires several hours or even more than ten hours, depending on the problem complexity (e.g., co-scheduling of multiple understaffed wards).

This project (Nurse Scheduling System, or 護理排班系統 in Mandarin) aims to develop a flexible web app to automate the nurse scheduling task, and to provide a unified framework for modeling all types of real-world scenarios without sacrificing flexibility.

> This project is in active development. Breaking changes may occur without notice. Please proceed with caution. Although the current version has been verified by domain experts and used successfully (with minimal post-adjustment) in several complex multi-ward scenarios involving up to ~100 nurses, it currently has a steep learning curve and lacks proper documentation.

## Privacy Notice

This early work-in-progress project provides basic privacy protections, including anonymizing individual people IDs, removing descriptions where possible, and privacy-masking Sentry session replays. The hosted application uses analytics and error reporting, and sends scheduling data to the selected backend when you click **Optimize**. Ad blockers may block analytics and error reporting, but not optimization submissions. Do not submit sensitive information. See [Privacy and Data Handling](https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md) for details.

## How to run

### Prerequisites

- [bun](https://bun.com/docs/installation) (for frontend development).
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (for backend development).
- [Docker](https://docs.docker.com/engine/install/ubuntu/) (optional, for Docker-based development environment and GPU solver).
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (optional, for GPU solver).

These are not hard requirements. If you know what you are doing, you can also use other tools to manage dependencies, such as [`nvm`/`npm`](https://nodejs.org/en/download) for Next.js, and `virtualenv` or `conda` for Python.

### Quick Start

Clone the repository:

```sh
git clone https://github.com/j3soon/nurse-scheduling.git
cd nurse-scheduling
```

#### Linux (bash/zsh)

Start frontend:

```sh
cd web-frontend
bun install
bun run dev
```

In a new terminal, start backend:

```sh
cd core
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
fastapi dev nurse_scheduling/serve.py
```

#### macOS (bash/zsh)

> macOS support is experimental.

Start frontend:

```sh
cd web-frontend
bun install
bun run dev
```

In a new terminal, start backend:

```sh
cd core
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
fastapi dev nurse_scheduling/serve.py
```

#### Windows (PowerShell)

> Windows OS support is experimental.

Start frontend:

```powershell
cd web-frontend
bun install
bun run dev
```

In a new terminal, start backend:

```powershell
cd core
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
uv venv --python 3.12
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
fastapi dev nurse_scheduling\serve.py
```

### Linux Development and Docker

The commands below are Linux-focused reference material for setup, testing, and Docker.

For Linux only: to quickly set up all local environments (`core`, `web-frontend`, and `docs`) in one go, run:

```sh
./scripts/setup_env.sh
```

For Docker-based development environment:

CPU image:

```sh
# build image
docker build -f docker/Dockerfile -t j3soon/nurse-scheduling:dev .
```

```sh
# persist Codex/Claude Code/OpenCode auth/config across containers
mkdir -p ~/docker/.codex
mkdir -p ~/docker/.claude
touch ~/docker/.claude.json
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
# mount project files and Codex/Claude Code/OpenCode config
docker run --rm -it --network=host \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/.claude:/root/.claude \
  -v ~/docker/.claude.json:/root/.claude.json \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  j3soon/nurse-scheduling:dev
```

GPU image with cuOpt support:

```sh
# build image with cuOpt support
docker build -f docker/Dockerfile.cuopt -t j3soon/nurse-scheduling:dev-cuopt .
```

The cuOpt image omits `highspy` because the pinned release has no CPython 3.14
wheel. Use another environment for the `pulp/highs` solver.

```sh
# persist Codex/Claude Code/OpenCode auth/config across containers
mkdir -p ~/docker/.codex
mkdir -p ~/docker/.claude
touch ~/docker/.claude.json
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
# mount project files and Codex/Claude Code/OpenCode config
docker run --rm -it --gpus all --network=host \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/.claude:/root/.claude \
  -v ~/docker/.claude.json:/root/.claude.json \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  j3soon/nurse-scheduling:dev-cuopt
```

After entering a container, use the [Core](#core) commands to run the CLI or
the [Web Backend](#web-backend) commands to start a server. Use the GPU image
for `pulp/cuopt`.

or with X11 forwarding for running Playwright interactive mode in the container:

```sh
xhost +local:docker
mkdir -p ~/docker/.codex
mkdir -p ~/docker/.claude
touch ~/docker/.claude.json
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
# mount project files and Codex/Claude Code/OpenCode config, and forward X11 display
docker run --rm -it --network=host \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/.claude:/root/.claude \
  -v ~/docker/.claude.json:/root/.claude.json \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  j3soon/nurse-scheduling:dev
```

> May need to run `rm -rf .next` in `web-frontend` to clear the Next.js cache when switching between host and Docker environments.

### Web Frontend

The commands below are tested on Linux only.

```sh
cd web-frontend
bun install
bun run dev
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

When using the repository `docker/Dockerfile`, Chromium is preinstalled in the image at
build time using the frontend's locked Playwright version. If you rebuild the
image after Playwright version changes, `bun run test:e2e` and
`bun run test:e2e:ui` should not require rerunning `bunx playwright install chromium`
inside each new `docker run --rm` container.

> For the interactive UI mode, you may need to run the tests multiple times to get it passed, as the test is currently somewhat flaky. This is due to the delay of page update and is planned to be fixed in the future.

In GitHub Actions, frontend browser integration tests run after frontend unit/coverage tests. The workflow uploads Playwright reports as build artifacts so failed CI runs keep browser traces and reports for debugging.

Generate a separate browser-flow coverage report from Playwright:

```sh
cd web-frontend
bun run test:e2e:coverage
bun run coverage:e2e:report
```

This writes a separate report under `web-frontend/coverage-e2e/` and does not replace the main Vitest coverage report under `web-frontend/coverage/`.

For building static site, run:

```sh
cd web-frontend
bun run build
```

For linting, run:

```sh
cd web-frontend
bun run lint -- --fix
```

> `bun` can be replaced directly with `npm` for the basic Next.js workflow, but the documented project scripts assume Bun.

### Core

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
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
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

### Web Backend

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

For a graphical browser, run
[Redis Insight](https://redis.io/docs/latest/operate/redisinsight/install/install-on-docker/)
on the Compose network:

```sh
docker run --rm \
  --name redisinsight \
  --network nurse-scheduling-backend_default \
  -p 127.0.0.1:5540:5540 \
  -v redisinsight:/data \
  redis/redisinsight:latest
```

Open `http://localhost:5540` and add a database with `redis://default@redis:6379`. Filter the Browser view with
`nurse_scheduling:jobs:v0:*`.

When Redis Insight runs on a remote VM, forward its locally bound port before
opening it in a local browser:

```sh
ssh -L 5540:127.0.0.1:5540 user@your-server
```

Keep Redis and Redis Insight off public interfaces. Redis Insight can modify or
delete stored data.

To run one backend worker with process-local memory and no Redis service, use
the pre-Redis deployment configuration:

```sh
cd docker
docker compose -f compose.backend.memory.yml up -d --build
```

The bundled Redis service uses its default RDB snapshot policy with a persistent
volume. Enable AOF or use a managed persistence policy when the deployment
requires a smaller data-loss window after an abrupt Redis or host failure.

### Documentation

The commands below are tested on Linux only.

```sh
cd docs
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
# preview documentation
mkdocs serve
```

For building static site, run:

```sh
cd docs
mkdocs build
```

## Acknowledgments

This project would not have been possible without the contributors in [CONTRIBUTORS.md](https://github.com/j3soon/nurse-scheduling/blob/dev/CONTRIBUTORS.md).

## License

This project is licensed under the [AGPL-3.0 License](https://github.com/j3soon/nurse-scheduling/blob/dev/LICENSE).

## References

- [Nurse rostering - Timefold](https://timefold.ai/docs/timefold-solver/latest/use-cases-and-examples/nurse-rostering/nurse-rostering.html)
- [A nurse scheduling problem - OR-Tools](https://developers.google.com/optimization/scheduling/employee_scheduling#a_nurse_scheduling_problem)
- Haspeslagh et al., 2010, [First International Nurse Rostering Competition 2010](https://nrpcompetition.kuleuven-kulak.be/wp-content/uploads/2020/06/nrpcompetition_description.pdf) [[website](https://nrpcompetition.kuleuven-kulak.be/)]
- Ceschia et al., 2015, [Second International Nurse Rostering Competition (INRC-II) --- Problem Description and Rules ---](https://arxiv.org/abs/1501.04177) [[website](https://mobiz.vives.be/inrc2/)]
