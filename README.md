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

## How to run

### Prerequisites

- [bun](https://bun.com/docs/installation).
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
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

#### Windows (PowerShell)

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

```sh
# build image
docker build -f Dockerfile -t j3soon/nurse-scheduling:dev .
# or optionally with cuOpt
docker build -f Dockerfile.cuopt -t j3soon/nurse-scheduling:dev-cuopt .
```

CPU solver:

```sh
# persist Codex/OpenCode auth/config across containers
mkdir -p ~/docker/.codex
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
# mount project files and Codex/OpenCode config
docker run --rm -it --network=host \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  j3soon/nurse-scheduling:dev
```

GPU solver:

```sh
# persist Codex/OpenCode auth/config across containers
mkdir -p ~/docker/.codex
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
# mount project files and Codex/OpenCode config
docker run --rm -it --gpus all --network=host \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  j3soon/nurse-scheduling:dev-cuopt
```

or with X11 forwarding for running Playwright interactive mode in the container:

```sh
xhost +local:docker
mkdir -p ~/docker/.codex
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
# mount project files and Codex/OpenCode config, and forward X11 display
docker run --rm -it --network=host \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
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

When using the repository `Dockerfile`, Chromium is preinstalled in the image at
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

We currently support three solvers: OR-Tools/CP-SAT, PuLP/CBC, and PuLP/cuOpt.

- `ortools/cp-sat` is the default solver and the most battle-tested one.
- `pulp/cbc` is covered by the normal schedule regression suite and opt-in real-world smoke checks.
- `pulp/cuopt` is the GPU-accelerated solver. Its real-world smoke check is opt-in and skips when the backend is unavailable.

```sh
cd core
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
# run CLI with default solver (ortools/cp-sat)
python -m nurse_scheduling.cli <input_file_path> [output_csv_path]
# for example:
python -m nurse_scheduling.cli tests/testcases/basics/01_1nurse_1shift_1day.yaml
# run CLI with PuLP/CBC solver
python -m nurse_scheduling.cli <input_file_path> [output_csv_path] --solver pulp/cbc
# explicit OR-Tools/CP-SAT selector
python -m nurse_scheduling.cli <input_file_path> [output_csv_path] --solver ortools/cp-sat
# run CLI with prettify and verbose
python -m nurse_scheduling.cli <input_file_path> [output_xlsx_path] --verbose --prettify
# record solver progress as JSON Lines for later plotting
python -m nurse_scheduling.cli tests/testcases/real/large-ward-with-87-people-2025-11.yaml --verbose --prettify --timeout 180 --progress-output progress.jsonl
```

Run tests:

```sh
cd core
# run low-level solver encoding tests
pytest --log-cli-level=INFO tests/test_solver_ortools_cp_sat.py
pytest --log-cli-level=INFO tests/test_solver_pulp_cbc.py
pytest --log-cli-level=INFO tests/test_solver_pulp_cuopt.py
# run schedule regression tests (OR-Tools / PuLP)
pytest --log-cli-level=INFO tests/test_schedule_ortools_cp_sat.py
pytest --log-cli-level=INFO tests/test_schedule_pulp_cbc.py
pytest --log-cli-level=INFO tests/test_schedule_pulp_cuopt.py
# run the normal core test suite
pytest --log-cli-level=INFO
# run the slower bounded real-world scenario checks explicitly
pytest --log-cli-level=INFO \
  tests/real/schedule_ortools_cp_sat.py \
  tests/real/schedule_pulp_cbc.py \
  tests/real/schedule_pulp_cuopt.py
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
pytest --log-cli-level=DEBUG tests/test_solver_ortools_cp_sat.py
pytest --log-cli-level=DEBUG tests/test_solver_pulp_cbc.py
pytest --log-cli-level=DEBUG tests/test_schedule_ortools_cp_sat.py
pytest --log-cli-level=DEBUG tests/test_schedule_pulp_cbc.py
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

(TODO: Production mode instructions are not yet completed.)

<!--
# or in production mode
fastapi run serve.py --port 8000 --workers 4
-->

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

This project would not have been possible without the contributions of [@ijsun](https://github.com/ijsun) and Jennifer Tzeng.

You can find the full list of code contributors [here](https://github.com/j3soon/nurse-scheduling/graphs/contributors).

## License

This project is licensed under the [AGPL-3.0 License](https://github.com/j3soon/nurse-scheduling/blob/main/LICENSE).

## References

- [Nurse rostering - Timefold](https://timefold.ai/docs/timefold-solver/latest/use-cases-and-examples/nurse-rostering/nurse-rostering.html)
- [A nurse scheduling problem - OR-Tools](https://developers.google.com/optimization/scheduling/employee_scheduling#a_nurse_scheduling_problem)
- Haspeslagh et al., 2010, [First International Nurse Rostering Competition 2010](https://nrpcompetition.kuleuven-kulak.be/wp-content/uploads/2020/06/nrpcompetition_description.pdf) [[website](https://nrpcompetition.kuleuven-kulak.be/)]
- Ceschia et al., 2015, [Second International Nurse Rostering Competition (INRC-II) --- Problem Description and Rules ---](https://arxiv.org/abs/1501.04177) [[website](https://mobiz.vives.be/inrc2/)]
