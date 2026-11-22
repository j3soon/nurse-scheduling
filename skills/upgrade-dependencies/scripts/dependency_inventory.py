"""List pinned toolchain versions, GitHub Actions, and container images, and flag drift."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
UNPINNED = ""

# (surface, file globs, pattern). The first group is the version. A pattern that
# matches without the group marks an unpinned installer.
FILE_RULES = [
    (
        "bun",
        ["docker/Dockerfile*"],
        r"bun\.sh/install \| bash(?: -s \"?bun-v([\w.]+))?",
    ),
    ("bun", ["netlify.toml"], r"BUN_VERSION\s*=\s*\"([\w.]+)\""),
    ("uv", ["docker/Dockerfile*"], r"ghcr\.io/astral-sh/uv:([\w.]+)"),
    ("uv", ["netlify.toml"], r"pip install uv==([\w.]+)"),
    ("python", ["docker/Dockerfile.api*"], r"^FROM python:(\d+\.\d+)"),
    ("python", ["netlify.toml"], r"PYTHON_VERSION\s*=\s*\"(\d+\.\d+)\""),
    (
        "python",
        ["scripts/setup_env.sh", "README.md", "docs/README.md"],
        r"--python (\d+\.\d+)",
    ),
    ("node (Netlify build)", ["netlify.toml"], r"NODE_VERSION\s*=\s*\"(\d+)\""),
    (
        "node (dev image CLIs)",
        ["docker/Dockerfile*"],
        r"nodesource\.com/setup_(\d+)\.x",
    ),
]
IMAGE_RULES = [
    (["docker/Dockerfile*", "docker/**/*.Dockerfile"], r"^FROM\s+(\S+)"),
    (["docker/compose*.yml"], r"^\s+image:\s*(\S+)"),
    (["scripts/pull_compose_base_images.sh"], r"^\s+\"(\S+)\"$"),
]
PRERELEASE = re.compile(
    r"\d(?:a|b|rc)\d*(?:[-.]|$)|alpha|beta|canary|nightly", re.IGNORECASE
)
GITHUB_RELEASES = {"bun": "oven-sh/bun", "uv": "astral-sh/uv"}


@dataclass(frozen=True)
class Pin:
    surface: str
    value: str
    path: str
    line: int


def _lines(root: Path, globs: list[str]):
    seen = set()
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                relative = path.relative_to(root).as_posix()
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1
                ):
                    yield relative, number, line


def _workflow_pins(root: Path) -> list[Pin]:
    pins = []
    current_path, action = "", ""
    for path, number, line in _lines(
        root, [".github/workflows/*.yaml", ".github/workflows/*.yml"]
    ):
        if path != current_path:
            current_path, action = path, ""
        if match := re.search(r"uses:\s*([\w.-]+/[\w.-]+)[\w./-]*@(\S+)", line):
            action = match.group(1)
            pins.append(Pin(f"action {action}", match.group(2), path, number))
        elif match := re.search(r"bun-version:\s*['\"]?([\w.]+)", line):
            pins.append(Pin("bun", match.group(1), path, number))
        elif match := re.search(r"python-version:\s*\[?\s*['\"](\d+\.\d+)['\"]", line):
            pins.append(Pin("python", match.group(1), path, number))
        elif (
            match := re.search(r"^\s+version:\s*['\"]?([\w.]+)", line)
        ) and action == "astral-sh/setup-uv":
            pins.append(Pin("uv", match.group(1), path, number))
    return pins


def _image_pins(root: Path) -> list[Pin]:
    pins = []
    for globs, pattern in IMAGE_RULES:
        for path, number, line in _lines(root, globs):
            match = re.search(pattern, line)
            if not match or "$" in match.group(1):
                continue
            name, _, tag = match.group(1).partition(":")
            pins.append(
                Pin(
                    f"image {name}",
                    UNPINNED if tag in ("", "latest") else tag,
                    path,
                    number,
                )
            )
    return pins


def collect(root: Path) -> list[Pin]:
    pins = _workflow_pins(root) + _image_pins(root)
    for surface, globs, pattern in FILE_RULES:
        for path, number, line in _lines(root, globs):
            if match := re.search(pattern, line):
                pins.append(Pin(surface, match.group(1) or UNPINNED, path, number))
    return pins


def problems(pins: list[Pin]) -> tuple[list[str], list[str]]:
    """Return errors that fail --check and warnings that need review."""
    errors, warnings = [], []
    surfaces: dict[str, list[Pin]] = {}
    for pin in pins:
        surfaces.setdefault(pin.surface, []).append(pin)
    for surface, group in sorted(surfaces.items()):
        values = sorted({pin.value for pin in group if pin.value})
        if len(values) > 1:
            errors.append(f"{surface}: conflicting pins {', '.join(values)}")
        for pin in group:
            where = f"{pin.path}:{pin.line}"
            if not pin.value:
                warnings.append(f"{surface}: unpinned or latest at {where}")
            elif PRERELEASE.search(pin.value):
                warnings.append(f"{surface}: prerelease {pin.value} at {where}")
            elif surface.startswith("node") and int(pin.value) % 2:
                warnings.append(
                    f"{surface}: Node {pin.value} is not an LTS line at {where}"
                )
    return errors, warnings


def _github_latest(repo: str) -> str:
    if (
        shutil.which("gh")
        and subprocess.run(
            ["gh", "auth", "status"], capture_output=True, check=False
        ).returncode
        == 0
    ):
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases/latest", "--jq", ".tag_name"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["tag_name"]


def _node_lts() -> str:
    with urllib.request.urlopen(
        "https://nodejs.org/dist/index.json", timeout=30
    ) as response:
        release = next(item for item in json.load(response) if item["lts"])
    return f"{release['version']} ({release['lts']})"


def latest_versions(surfaces: set[str]) -> dict[str, str]:
    lookups = {
        surface: (_github_latest, GITHUB_RELEASES[surface])
        for surface in surfaces
        if surface in GITHUB_RELEASES
    }
    for surface in surfaces:
        if surface.startswith("action "):
            lookups[surface] = (_github_latest, surface.removeprefix("action "))
        elif surface.startswith("node"):
            lookups[surface] = (lambda _: _node_lts(), "")
    latest = {}
    for surface, (lookup, argument) in sorted(lookups.items()):
        try:
            latest[surface] = lookup(argument)
        except (
            OSError,
            ValueError,
            KeyError,
            StopIteration,
            subprocess.SubprocessError,
        ) as error:
            latest[surface] = f"unknown ({type(error).__name__})"
    return latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="repository root"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when one surface has conflicting pins",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="look up upstream releases (uses the network)",
    )
    args = parser.parse_args(argv)

    pins = collect(args.root)
    latest = latest_versions({pin.surface for pin in pins}) if args.latest else {}
    surfaces: dict[str, list[Pin]] = {}
    for pin in pins:
        surfaces.setdefault(pin.surface, []).append(pin)
    for surface, group in sorted(surfaces.items()):
        values = ", ".join(sorted({pin.value or "unpinned" for pin in group}))
        suffix = f"  (latest: {latest[surface]})" if surface in latest else ""
        print(f"{surface}: {values}{suffix}")
        for pin in group:
            print(f"  {pin.value or 'unpinned'}  {pin.path}:{pin.line}")

    errors, warnings = problems(pins)
    for label, items in (("Errors", errors), ("Warnings", warnings)):
        if items:
            print(f"\n{label}:")
            for item in items:
                print(f"  {item}")
    return 1 if args.check and errors else 0


if __name__ == "__main__":
    sys.exit(main())
