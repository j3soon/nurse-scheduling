---
name: upgrade-dependencies
description: Upgrade the repository's dependencies for security fixes and long-term maintenance in a dedicated worktree and pull request. Covers the core and docs uv locks and their exact pins, the E2B template pins, frontend Bun packages including Next.js, the Bun, uv, Node, and Python versions, GitHub Actions tags, container images including the optional move of the cuOpt image to a stable release, the vendored OpenCC bundle, and the yearly Taiwan holiday data. Use when asked to upgrade, update, or bump dependencies, fix dependency advisories, or list what is outdated. Do not use for the security scan of the running services (security-scan).
---

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Upgrade Dependencies

Upgrade dependencies to receive security fixes and to keep each later upgrade
small. Fix known advisories first. Then apply routine updates.

## 1. Start a dedicated worktree

Unless the user says otherwise, do every upgrade in its own worktree and merge
it through its own pull request. From the main clone:

```bash
git fetch https://github.com/j3soon/nurse-scheduling.git dev
scripts/add_worktree.sh chore/upgrade-deps-YYYY-MM FETCH_HEAD
cd .worktrees/chore/upgrade-deps-YYYY-MM
# Each worktree has its own FETCH_HEAD. Fetch again for the later comparisons.
git fetch https://github.com/j3soon/nurse-scheduling.git dev
(cd web-frontend && bun install --frozen-lockfile)
```

Use one pull request for the routine updates. Give a major version that needs
code changes its own worktree and pull request, such as
`chore/upgrade-next-17`. This applies to Next.js, React, ESLint, TypeScript,
Vitest, PuLP, `pypdf`, and PostgreSQL majors, a Python or Node version change,
and a new cuOpt base image. A separate pull request keeps a risky change easy
to review and revert. Report each deferred major in the routine pull request.

## 2. Take the inventory

```bash
python skills/upgrade-dependencies/scripts/dependency_inventory.py --latest
```

The script lists every pinned Bun, uv, Node, and Python version, GitHub Actions
tag, and container image tag with its file locations. It reports conflicting
pins as errors, and unpinned or `latest` references, prerelease tags, and Node
lines without long-term support (LTS) as warnings. `--latest` adds the upstream
releases for Bun, uv, Node, and each action. It uses `gh` when it is
authenticated and otherwise the unauthenticated GitHub API, which allows 60
requests per hour. CI runs the script with `--check`, which fails on
conflicting pins.

List the package updates and advisories:

```bash
(cd core && uv tree --outdated --depth 1 --all-groups --python-version 3.14)
(cd docs && uv tree --outdated --depth 1)
(cd web-frontend && bun outdated && bun audit)
```

Audit the locked Python packages with the commands in step 5 of
`skills/security-scan`. Record each advisory and its fixed version for the pull
request description.

## 3. Upgrade one area per commit

Commit each area after its checks pass. Update all locations of a version in the
same commit.

Change each manifest and lock with the tool that owns it, because a hand edit
can leave the two out of step. Use `uv add`, `uv remove`, and `uv lock` for
`pyproject.toml` and `uv.lock`. Use `bun add`, `bun remove`, `bun update`, and
`bun pm pkg set` for `package.json` and `bun.lock`. Edit a file by hand only
when no tool writes the value, such as a comment, `[tool.uv]` constraints, a
workflow tag, a Dockerfile, a Compose file, or `netlify.toml`.

### Record the tool commands

End the body of each commit that changes a lock with a record of the bun and uv
commands, before the attribution line. Write one line for each command, in the
order that you ran them from the repository root. Name each file that the
command wrote, with `generates` for a new file and `updates` for a changed
file. `uv add` and `bun update` also update the lock. Write a single line
without a bullet:

```text
`cd core && uv lock` generates `core/uv.lock`.
```

Write two or more lines as a bullet list. Shorten a long command with short
options, such as `-P` for `--upgrade-package`.

Do not record hand edits of files that no tool owns, such as workflow tags,
Dockerfiles, Compose files, `netlify.toml`, or comments. The diff shows them.
Do not repeat what the body already says. Add a hand edit line only when you
change a version in `package.json` or `pyproject.toml` by hand, because no tool
writes that value. Give the reason after `because`:

```text
- A hand edit updates `core/pyproject.toml`, because no uv command edits `[tool.uv] constraint-dependencies`.
- `cd core && uv lock -P pandas` updates `core/uv.lock`.
```

Check the records before you push:

```bash
python skills/upgrade-dependencies/scripts/check_upgrade_commits.py FETCH_HEAD..HEAD
```

The script reports a changed lock that no bun or uv line names, and a named
file that the commit does not change. It also reports a hand edit line for a
file that no tool owns.

### Core Python packages

- Run `uv lock --upgrade` in `core/`. Use `uv lock --upgrade-package NAME` for
  one package.
- Review the exact `==` pins in `core/pyproject.toml`. Some pins predate
  `uv.lock` and exist only for reproducibility, which the lock now provides.
  Find the reason for each pin with
  `git log -G'NAME==' -- core/pyproject.toml core/requirements.txt core/requirements-optional.txt`.
  Keep a pin only when it has a reason, and state that reason in a comment.
  Replace the other pins with a lower bound through `uv add`, such as
  `uv add --no-sync --group sandbox 'pypdf>=7.1.1'`. Pass `--optional EXTRA`,
  `--group GROUP`, or `--dev` for the table that holds the package. A lower
  bound keeps the locked version, so then run `uv lock -P NAME`. `uv add` does
  not write comments, so add the reason comment by hand.
- These pins have known reasons:
  - `ortools` keeps solver results deterministic. Review the changed expected
    results when you upgrade it.
  - `pyscipopt` bundles the SCIP version behind `pulp/scip`, whose regression
    tests compare exact schedules.
  - `highspy` must match the HiGHS version that OR-Tools bundles. Another
    version in the same process crashes OR-Tools MathOpt HiGHS solves.
    Upgrade it with `ortools`.
  - `e2b` was verified live for the timeout and pause behavior that
    `docker/e2b/README.md` describes. Upgrade it only with the live E2B check.
  - `ty` adds diagnostics in new pre-1.0 releases. Fix its new findings in the
    same commit.
- The compact core suite skips the optional solvers. After a solver pin
  changes, also run
  `pytest -q --solver-profile=all tests/test_schedule_pulp_*.py tests/test_schedule_ortools_*.py`.
- The E2B template installs the `sandbox` group. Copy the locked versions of
  those packages into `docker/e2b/e2b.Dockerfile`, then run
  `pytest -q tests/test_dependency_lock.py` in `core/`.
- The `[tool.uv]` constraints hold NumPy and pandas back for the cuOpt image.
  Change them only with the cuOpt base image.
- Test in a temporary Python 3.14 environment, which matches CI. Do not sync the
  dev container's `/opt/venv` from an upgrade worktree. All worktrees in the
  container share it.

  ```bash
  venv="$(mktemp -d)/venv"
  (cd core && UV_PROJECT_ENVIRONMENT="$venv" uv sync --locked --all-extras --python 3.14)
  (cd core && PATH="$venv/bin:$PATH" VIRTUAL_ENV="$venv" ../scripts/test_core_affected.sh --base FETCH_HEAD)
  ```

  A lock change runs the full compact core suite.
- A changed template pin needs a template rebuild. The AI server rebuilds the
  template at startup. Ask the user to run the live check from
  `docker/e2b/README.md`, because it uses their E2B account.

### Docs Python packages

- Run `uv lock --upgrade --project docs`. Change an exact pin with
  `uv add --project docs --no-sync 'zensical==X.Y.Z'`. Zensical is a pre-1.0
  package, so read its release notes.
- Build the site and check its links with the commands in `docs/AGENTS.md`.

### Frontend packages

- `bun outdated` shows the newest version inside each `package.json` range and
  the latest release. `bun update` stays inside the ranges, so it does not
  change exact pins. Set an exact pin with `bun add --exact NAME@VERSION`, or
  `bun add --exact -d` for a development dependency.
- Keep `next` and `eslint-config-next` at the same version. Keep `react` and
  `react-dom` at the same version. Keep the `@types/react` and
  `@types/react-dom` overrides equal to their development dependencies.
- Upgrade one major version per commit, and follow its upstream migration
  guide.
- After a `@playwright/test` update, run `bunx playwright install chromium`.
  CI and the dev image install the matching browser.
- Run `bun audit` again. The site is a static export, so Next.js server
  advisories do not reach production. Still upgrade to the fixed version.
- When a parent's range blocks the fixed version of a transitive package, add
  a nested entry to `overrides` with
  `bun pm pkg set 'overrides.exceljs.uuid=^11.1.1'`, then run `bun install`.
  A top-level entry also replaces the package for other parents that need an
  older major. Exercise the parent's code path that uses the package. Remove
  the entry when `bun why NAME` shows that the parent accepts a fixed version.
- Run the lint, build, unit, and E2E commands in `web-frontend/AGENTS.md`.

### Toolchain versions

Update every location that the inventory lists:

- **Bun:** `bun-version` in the workflows, `BUN_VERSION` in `netlify.toml`,
  and the installer in the dev Dockerfiles, which takes `bash -s "bun-vX.Y.Z"`.
- **uv:** `version` in the workflows, the `ghcr.io/astral-sh/uv` tags in the
  Dockerfiles, and `uv==` in `netlify.toml`. Then run `uv lock` in `core/` and
  `docs/`. A newer uv can rewrite lock metadata. Commit that change with the
  version change.
- **Node:** `node-version` in the frontend workflows, `NODE_VERSION` in
  `netlify.toml`, and the NodeSource line in the dev Dockerfiles. Use an LTS
  line, which has an even major version.
- **Python:** `python-version` in the workflows, the API base images,
  `PYTHON_VERSION` in `netlify.toml`, and `--python` in `docker/Dockerfile.dev`,
  `scripts/setup_env.sh`, and the READMEs. A new Python minor version needs its own pull request.

### GitHub Actions

- Update the tags in every workflow. Use tags, not commit SHAs, as
  `.github/AGENTS.md` requires.
- A new major version can rename inputs or change defaults. Read its release
  notes before you change the tag.

### Container images

- **Service images:** `docker/compose*.yml` sets PostgreSQL, Redis, NGINX,
  pgAdmin, RedisInsight, and cloudflared. Update every Compose variant and
  `scripts/pull_compose_base_images.sh` together. Keep cloudflared on its
  `latest` tag. The inventory warning for it is expected.
  A PostgreSQL major version needs a data migration for the existing volume.
- **Base images:** `python:3.14-slim` for the API, `ubuntu:24.04` for the dev
  image, and `e2bdev/base` for the E2B template.
- A rebuild with `--pull` refreshes `latest` tags and the APT packages, even
  when no tag changes. Ask the user to rebuild on the host, for example
  `docker compose -f docker/compose.backend.yml build --pull`.
- **cuOpt base image (optional):** prefer a stable release tag of
  `nvidia/cuopt` over an alpha tag, such as `26.8.0a`. A new base image can
  change the Python, NumPy, pandas, and Numba versions. Update the `highspy`
  marker and the `[tool.uv]` constraints in `core/pyproject.toml` to match.
  Then ask the user to rebuild the image and run the cuOpt tests on a GPU host.
  Stay on cuOpt 26.8.0 until a release fixes the status bug in 26.10.1. When
  presolve removes the whole problem, 26.10.1 reports `FeasibleFound` instead
  of `Optimal`, so `tests/test_schedule_pulp_cuopt.py` fails.

### Vendored code and data

- **OpenCC:** `python scripts/check_vendor.py --upstream` compares the bundle
  with its pinned npm package. Follow the upgrade steps in
  `thirdparty/opencc/README.md`.
- **Taiwan holidays:** MODA publishes each new year's office calendar CSV. Add
  it to `thirdparty/moda-opendata/` and extend
  `web-frontend/src/utils/taiwanHolidays.ts` in a separate pull request. The
  README in that directory gives the `uv run` commands.
  `git log -- thirdparty/moda-opendata` shows the previous additions.
- **Dev image agent CLIs:** the dev Dockerfiles install the latest Codex,
  Claude Code, and opencode releases. A dev image rebuild updates them.

## 4. Finish

1. Run the full local CI with `skills/run-ci`.
2. Run the inventory with `--check`, `check_upgrade_commits.py FETCH_HEAD..HEAD`,
   and `git diff --check FETCH_HEAD`.
3. Write the pull request description. List the old and new versions for each
   area, the fixed advisories, and the deferred majors with their reasons. Name
   the checks that the user must run on the host: image builds, the live E2B
   check, the cuOpt GPU tests, and the Netlify deploy preview.
4. Ask the user to push from the host when the container cannot push. Create the
   pull request with `gh pr create` when `gh` is authenticated.
5. After the merge, remove the worktree with `scripts/remove_worktree.sh`.

Repeat the routine upgrade every month. Fix a published advisory at once.
Add the holiday data once a year. Plan a Python or Node version change before
the current version reaches its end of support.
