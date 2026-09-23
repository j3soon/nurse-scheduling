# Nurse Scheduling System

[![tests](https://img.shields.io/github/actions/workflow/status/j3soon/nurse-scheduling/test-core.yaml?label=tests)](https://github.com/j3soon/nurse-scheduling/actions/workflows/test-core.yaml)
[![Netlify Status](https://api.netlify.com/api/v1/badges/8ec5c5da-89e1-41e5-87b3-133ce1007783/deploy-status)](https://nursescheduling.org/)
[![codecov](https://codecov.io/github/j3soon/nurse-scheduling/branch/dev/graph/badge.svg)](https://codecov.io/github/j3soon/nurse-scheduling)
[![docs](https://img.shields.io/badge/docs-online-blue?logo=googledocs)](https://nursescheduling.org/docs/)

An automated nurse schedule optimization system designed for diverse and complex real-world requirements.

- Stable version hosted at [nursescheduling.org](https://nursescheduling.org/).
- Latest development features hosted at [dev.nursescheduling.org](https://dev.nursescheduling.org/).
- Versioned releases remain available at URLs such as [release-0-2.nursescheduling.org](https://release-0-2.nursescheduling.org/).
- Documentation hosted at [nursescheduling.org/docs](https://nursescheduling.org/docs/).
- Source code hosted on [GitHub](https://github.com/j3soon/nurse-scheduling).

## Introduction

The nurse scheduling (or employee scheduling) problem is a well-known problem in the field of operations research (OR) and can be (approximately) solved efficiently by constrained optimization.

However, constraints can differ greatly between hospitals and wards, and there is currently no unified framework for modeling these diverse requirements. Most existing literature focuses on modeling an over-simplified constraint set, which is not applicable to real-world situations. Therefore, in practice, the problem is still often solved by hand with the help of Excel, which is often extremely time-consuming. The entire process requires several hours or even more than ten hours, depending on the problem complexity (e.g., co-scheduling of multiple understaffed wards).

This project (Nurse Scheduling System, or 護理排班系統 in Mandarin) provides a flexible web app and framework for automating schedule optimization across real-world scenarios. It has generated schedules used by real wards with minimal post-adjustment. We keep the main deployment stable, publish the latest features separately, retain versioned releases, and strive to preserve backward compatibility.

Development builds may introduce breaking changes. Use the stable or versioned deployments when repeatability is important.

## Project Scope

This project focuses on the difficult and time-consuming part of rostering: turning staffing requirements, rules, and individual preferences into a good schedule. A scheduler still needs to define the ward's concrete rules. Infeasible staffing requirements may also require the scheduler to decide what can safely be relaxed. We continue to improve the ease and flexibility of expressing these constraints. Automated re-optimization also makes changed requests less costly and allows more preferences to be considered than a manual process often can.

The system complements rather than replaces a hospital's existing coordination and workforce-management processes. It intentionally does not prescribe user accounts, leave approvals, shift swaps, schedule publication, audit trails, or other self-service and governance workflows. Preferences can come from an existing hospital system, a spreadsheet, or paper and then be entered by the person preparing the schedule. In our on-site discussions, a head nurse or senior ward member typically owned this task, collecting requests was not the main bottleneck, and constructing or revising the schedule could take several hours or more than ten hours. Organizations can retain any required approvals and audit records in their existing systems.

Keeping request coordination separate makes the optimizer hospital-system agnostic and easier to adopt. Hospitals that need direct integration can import data into the scheduling format and export the result to their systems. Please [open an issue](https://github.com/j3soon/nurse-scheduling/issues) to discuss additional import or export requirements.

Two hosted optimization servers are provided as free, shared, best-effort services. The lower-capacity secondary server is available as a fallback. Please use them fairly and do not abuse them. You can also self-host the backend software from this repository.

## Milestones

The project began in 2023 as a proof of concept verified by domain experts in a multi-ward scenario. In late 2025 it moved into real wards: three complex multi-ward scenarios with about 100 nurses, where ward templates were built in the web GUI and refined with head nurses, and the schedules were put into use with minimal adjustments. Since then, non-developer assistants have generated final schedules for real ward operations by learning the workflow and reusing templates, with little or no developer support. The public, free optimization server went online in June 2026; as of July 2026 the primary server had accumulated over 99.9% uptime, with a lower-capacity secondary server as backup. See the [timeline](https://dev.nursescheduling.org/docs/timeline/) for dated details.

## Privacy Notice

The hosted application anonymizes individual people IDs and removes descriptions by default before sending a schedule for optimization. A schedule without direct identifiers may not identify anyone by itself, but dates, groups, and patterns can still be sensitive in context. Use nicknames or non-identifying IDs when in doubt. For greater control, self-host the open-source frontend and backend so your organization can inspect the code and apply its own security and retention policies. See [Privacy and Data Handling](https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md) for details.

## AI Beta Access

During the evaluation period, the hosted AI assistant is gated by an API key by default.

To request access for experimentation, email [admin@nursescheduling.org](mailto:admin@nursescheduling.org) from your institution email address. Include your institution's name and a short description of how you plan to evaluate the assistant.

Before requesting or using access, review [Privacy and Data Handling](https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md). Do not submit personal, confidential, regulated, or otherwise sensitive information.

## Support

For general questions, [open a GitHub issue](https://github.com/j3soon/nurse-scheduling/issues). For personal questions, email [admin@nursescheduling.org](mailto:admin@nursescheduling.org).

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

On Linux and macOS (bash), set up all local environments (`core`,
`web-frontend`, and `docs`) in one go:

```sh
./scripts/setup_env.sh
```

Then start the backend and the frontend in separate terminals:

```sh
./scripts/start_backend.sh
./scripts/start_frontend.sh
```

Open `http://localhost:3000`.

On Windows, use WSL and the same commands, or install the environments
manually with the commands in
[core/README.md](https://github.com/j3soon/nurse-scheduling/blob/dev/core/README.md)
and
[web-frontend/README.md](https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/README.md),
then use the same start scripts (WSL) or the PowerShell block below.

Module and deployment guides:

- Core (CLI, backend, AI backend, configuration, tests): [core/README.md](https://github.com/j3soon/nurse-scheduling/blob/dev/core/README.md)
- Web frontend (development, tests, builds, Netlify hosting): [web-frontend/README.md](https://github.com/j3soon/nurse-scheduling/blob/dev/web-frontend/README.md)
- Documentation site (preview and build): [docs/README.md](https://github.com/j3soon/nurse-scheduling/blob/dev/docs/README.md)
- Backend deployment (Docker Compose, tunnel, Sentry, reports): [docker/README.md](https://github.com/j3soon/nurse-scheduling/blob/dev/docker/README.md)

Local development needs no environment variables. The AI backend reads
`docker/.env` (copied from the tracked `docker/.env.example`) for its provider
and sandbox settings.

### Windows (PowerShell)

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

### Development container

The commands below are Linux-focused reference material for the Docker-based
development environment.

The development images include GitHub CLI. GitHub authentication is optional.
For read-only GitHub access, create a short-lived
[fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)
with access limited to this repository. Grant read-only repository permissions
for Contents, Pull requests, Issues, and Actions, then export it on the host:

```sh
export GH_TOKEN=github_pat_your_token
```

The run commands below pass `GH_TOKEN` into the container when it is set. Do not
put the token in the image, this repository, or a tracked environment file. Run
`gh auth status` inside the container to verify access.

CPU image:

```sh
# build image
docker build -f docker/Dockerfile.dev -t j3soon/nurse-scheduling:dev .
```

```sh
# persist Codex/Claude Code/OpenCode/Pi auth/config across containers
mkdir -p ~/docker/.codex
mkdir -p ~/docker/.claude
touch ~/docker/.claude.json
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
mkdir -p ~/docker/pi/agent
# mount project files and Codex/Claude Code/OpenCode/Pi config
docker run --rm -it --network=host \
  -e GH_TOKEN \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/.claude:/root/.claude \
  -v ~/docker/.claude.json:/root/.claude.json \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  -v ~/docker/pi/agent:/root/.pi/agent \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  j3soon/nurse-scheduling:dev
```

GPU image with cuOpt support:

```sh
# build image with cuOpt support
docker build -f docker/Dockerfile.dev.cuopt -t j3soon/nurse-scheduling:dev-cuopt .
```

The cuOpt image omits `highspy` because the pinned release has no CPython 3.14
wheel. Use another environment for the `pulp/highs` solver.

```sh
# persist Codex/Claude Code/OpenCode/Pi auth/config across containers
mkdir -p ~/docker/.codex
mkdir -p ~/docker/.claude
touch ~/docker/.claude.json
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
mkdir -p ~/docker/pi/agent
# mount project files and Codex/Claude Code/OpenCode/Pi config
docker run --rm -it --gpus all --network=host \
  -e GH_TOKEN \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/.claude:/root/.claude \
  -v ~/docker/.claude.json:/root/.claude.json \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  -v ~/docker/pi/agent:/root/.pi/agent \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  j3soon/nurse-scheduling:dev-cuopt
```

After entering a container, use the [Core](https://github.com/j3soon/nurse-scheduling/blob/dev/core/README.md)
commands to run the CLI or start a server. Use the GPU image
for `pulp/cuopt`.

To run the experimental AI backend in the container, add
`--env-file docker/.env` to `docker run` and see the AI backend section of the
[Core README](https://github.com/j3soon/nurse-scheduling/blob/dev/core/README.md).

or with X11 forwarding for running Playwright interactive mode in the container:

```sh
xhost +local:docker
mkdir -p ~/docker/.codex
mkdir -p ~/docker/.claude
touch ~/docker/.claude.json
mkdir -p ~/docker/opencode/.config/opencode
mkdir -p ~/docker/opencode/.local/share/opencode
mkdir -p ~/docker/pi/agent
# mount project files and Codex/Claude Code/OpenCode/Pi config, and forward X11 display
docker run --rm -it --network=host \
  -e GH_TOKEN \
  -v $(pwd):/app \
  -v ~/docker/.codex:/root/.codex \
  -v ~/docker/.claude:/root/.claude \
  -v ~/docker/.claude.json:/root/.claude.json \
  -v ~/docker/opencode/.config/opencode:/root/.config/opencode \
  -v ~/docker/opencode/.local/share/opencode:/root/.local/share/opencode \
  -v ~/docker/pi/agent:/root/.pi/agent \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  j3soon/nurse-scheduling:dev
```

> May need to run `rm -rf .next` in `web-frontend` to clear the Next.js cache when switching between host and Docker environments.

## Acknowledgments

This project would not have been possible without the contributors in [CONTRIBUTORS.md](https://github.com/j3soon/nurse-scheduling/blob/dev/CONTRIBUTORS.md).

See [ACKNOWLEDGMENTS.md](https://github.com/j3soon/nurse-scheduling/blob/dev/ACKNOWLEDGMENTS.md) for the free services this project relies on.

## License

This project is licensed under the [AGPL-3.0 License](https://github.com/j3soon/nurse-scheduling/blob/dev/LICENSE).

## References

- [Nurse rostering - Timefold](https://timefold.ai/docs/timefold-solver/latest/use-cases-and-examples/nurse-rostering/nurse-rostering.html)
- [A nurse scheduling problem - OR-Tools](https://developers.google.com/optimization/scheduling/employee_scheduling#a_nurse_scheduling_problem)
- Haspeslagh et al., 2010, [First International Nurse Rostering Competition 2010](https://nrpcompetition.kuleuven-kulak.be/wp-content/uploads/2020/06/nrpcompetition_description.pdf) [[website](https://nrpcompetition.kuleuven-kulak.be/)]
- Ceschia et al., 2015, [Second International Nurse Rostering Competition (INRC-II) --- Problem Description and Rules ---](https://arxiv.org/abs/1501.04177) [[website](https://mobiz.vives.be/inrc2/)]
