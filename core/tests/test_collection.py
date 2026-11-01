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


def test_normal_collection_never_imports_legacy_ai_tests(tmp_path):
    core = Path(__file__).resolve().parents[1]
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(core / "tests/conftest.py", tests / "conftest.py")
    selection = core / "tests/collection.py"
    if selection.exists():
        shutil.copyfile(selection, tests / selection.name)
    shutil.copyfile(core / "pyproject.toml", tmp_path / "pyproject.toml")
    for name in [
        "test_ai_eval_obsolete.py",
        "test_ai_ladder_audit.py",
        "test_ai_prefix_cache_probe.py",
        "test_ai_provider_preflight.py",
        "test_ai_read_batch_benchmark.py",
    ]:
        (tests / name).write_text('raise RuntimeError("Legacy test module must never be imported")\n', encoding="utf-8")
    legacy = tests / "ai_eval"
    legacy.mkdir()
    (legacy / "test_obsolete.py").write_text(
        'raise RuntimeError("Legacy package must never be collected")\n', encoding="utf-8"
    )
    (tests / "test_current.py").write_text("def test_current():\n    pass\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(core) + os.pathsep + os.environ.get("PYTHONPATH", "")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_current" in result.stdout
    assert "1 test collected" in result.stdout
