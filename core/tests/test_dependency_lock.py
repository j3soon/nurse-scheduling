"""Check that the E2B template installs the locked sandbox packages."""

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

# This test is mostly AI generated.

import re
from pathlib import Path

import tomllib

CORE_DIR = Path(__file__).resolve().parents[1]
E2B_DOCKERFILE = CORE_DIR.parent / "docker" / "e2b" / "e2b.Dockerfile"
TEMPLATE_PIN = re.compile(r"'([A-Za-z0-9._-]+)==([^']+)'")
REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9._-]+")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _template_pins() -> dict[str, str]:
    dockerfile = E2B_DOCKERFILE.read_text(encoding="utf-8")
    return {_normalize(name): version for name, version in TEMPLATE_PIN.findall(dockerfile)}


def _sandbox_group() -> set[str]:
    project = tomllib.loads((CORE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    return {_normalize(REQUIREMENT_NAME.match(entry).group()) for entry in project["dependency-groups"]["sandbox"]}


def _locked_versions() -> dict[str, set[str]]:
    lock = tomllib.loads((CORE_DIR / "uv.lock").read_text(encoding="utf-8"))
    versions: dict[str, set[str]] = {}
    for package in lock["package"]:
        if "version" in package:
            versions.setdefault(package["name"], set()).add(package["version"])
    return versions


def test_e2b_template_installs_exactly_the_sandbox_group():
    assert set(_template_pins()) == _sandbox_group()


def test_e2b_template_pins_match_the_lock():
    locked = _locked_versions()
    template = _template_pins()
    assert {name: locked.get(name) for name in template} == {name: {version} for name, version in template.items()}
