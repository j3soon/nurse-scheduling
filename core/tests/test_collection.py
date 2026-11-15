"""Collection boundaries for the active core test suite."""

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

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _collect(tmp_path, files, *options):
    core = Path(__file__).resolve().parents[1]
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(core / "tests/conftest.py", tests / "conftest.py")
    selection = core / "tests/collection.py"
    if selection.exists():
        shutil.copyfile(selection, tests / selection.name)
    shutil.copyfile(core / "pyproject.toml", tmp_path / "pyproject.toml")
    for name, content in files.items():
        path = tests / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *options, "tests"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(core) + os.pathsep + os.environ.get("PYTHONPATH", "")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result


def test_normal_collection_never_imports_legacy_ai_tests(tmp_path):
    files = dict.fromkeys(
        [
            "test_ai_eval_obsolete.py",
            "test_ai_ladder_audit.py",
            "test_ai_prefix_cache_probe.py",
            "test_ai_provider_preflight.py",
            "test_ai_read_batch_benchmark.py",
            "ai_eval/test_obsolete.py",
        ],
        'raise RuntimeError("Legacy test module must never be imported")\n',
    )
    files["test_current.py"] = "def test_current():\n    pass\n"
    result = _collect(tmp_path, files)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_current" in result.stdout
    assert "1 test collected" in result.stdout


@pytest.mark.parametrize("profile", ["primary", "all"])
def test_solver_profile_keeps_primary_sweeps_and_selects_optional_runtimes(tmp_path, profile):
    files = {
        name: "def test_schedule():\n    pass\n"
        for name in ["test_schedule_ortools_cp_sat.py", "test_schedule_pulp_cbc.py"]
    }
    files["test_schedule_pulp_glpk.py"] = (
        'raise RuntimeError("Optional solver must not be imported")\n'
        if profile == "primary"
        else "def test_glpk():\n    pass\n"
    )
    files["test_adapter.py"] = (
        "import pytest\n"
        "def test_unavailable_runtime():\n    pass\n"
        "@pytest.mark.requires_solver('pulp/highs')\n"
        "def test_optional_runtime():\n    pass\n"
    )
    result = _collect(tmp_path, files, f"--solver-profile={profile}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_schedule_ortools_cp_sat.py::test_schedule" in result.stdout
    assert "test_schedule_pulp_cbc.py::test_schedule" in result.stdout
    assert "test_adapter.py::test_unavailable_runtime" in result.stdout
    assert ("test_adapter.py::test_optional_runtime" in result.stdout) == (profile == "all")
    assert ("test_schedule_pulp_glpk.py::test_glpk" in result.stdout) == (profile == "all")
