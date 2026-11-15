"""Pytest options shared by the core test suite."""

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

import importlib.util
from functools import cache
from pathlib import Path

import pytest

from nurse_scheduling.server.solver_options import SOLVER_RUNTIME_MODULES, solver_is_available

from .collection import LEGACY_AI_TEST_PATTERNS

collect_ignore_glob = LEGACY_AI_TEST_PATTERNS

# Run the complete fixture corpus through CP-SAT and CBC. Other adapters retain
# low-level tests, while their repeated schedule sweeps remain available on demand.
OPTIONAL_SOLVER_TEST_FILES = {
    "test_export_xlsx_pulp_cbc.py",
    "test_schedule_ortools_mathopt_cp_sat.py",
    "test_schedule_ortools_mathopt_gscip.py",
    "test_schedule_ortools_mathopt_highs.py",
    "test_schedule_ortools_mpsolver_bop.py",
    "test_schedule_ortools_mpsolver_cbc.py",
    "test_schedule_ortools_mpsolver_cp_sat.py",
    "test_schedule_ortools_mpsolver_scip.py",
    "test_schedule_pulp_cuopt.py",
    "test_schedule_pulp_glpk.py",
    "test_schedule_pulp_highs.py",
    "test_schedule_pulp_scip.py",
    "test_solver_pulp_cuopt.py",
    "test_solver_pulp_glpk.py",
}


def pytest_ignore_collect(collection_path, config):
    if config.getoption("--solver-profile") == "primary" and collection_path.name in OPTIONAL_SOLVER_TEST_FILES:
        return True


@pytest.fixture
def legacy_text_encoding(monkeypatch: pytest.MonkeyPatch):
    """Expose implicit fixture decoding with a legacy Windows default on every platform."""
    read_text = Path.read_text

    def read_with_legacy_default(path, encoding=None, errors=None, **kwargs):
        return read_text(path, encoding="cp1252" if encoding is None else encoding, errors=errors, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_with_legacy_default)


def pytest_addoption(parser):
    parser.addoption(
        "--solver-profile",
        choices=("primary", "all"),
        default="all",
        help="Use primary for CP-SAT/CBC regression sweeps and OR-Tools adapter checks, or all for every backend.",
    )
    parser.addoption(
        "--skip-unavailable-solvers",
        action="store_true",
        help="Skip tests marked requires_solver when that optional solver runtime is not installed.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_solver(solver): the test needs this optional solver runtime")


def pytest_collection_modifyitems(config, items):
    skip_unavailable = config.getoption("--skip-unavailable-solvers")
    primary = config.getoption("--solver-profile") == "primary"
    available = cache(solver_is_available)
    selected, deselected = [], []
    for item in items:
        if primary and (
            item.path.name in OPTIONAL_SOLVER_TEST_FILES
            or any(
                marker.args[0].startswith("pulp/") and marker.args[0] != "pulp/cbc"
                for marker in item.iter_markers("requires_solver")
            )
        ):
            deselected.append(item)
            continue
        selected.append(item)
        for marker in item.iter_markers("requires_solver"):
            solver = marker.args[0]
            module = SOLVER_RUNTIME_MODULES.get(solver)
            if module is not None and importlib.util.find_spec(module) is None:
                # The dev image never ships this package, so the test cannot pass here. Skip it
                # without requiring the option.
                item.add_marker(pytest.mark.skip(reason=f"{solver} runtime package {module} is not installed"))
            elif skip_unavailable and not available(solver):
                # Without the option, an installed but failing runtime fails its tests, so CI
                # cannot pass with an incomplete install.
                item.add_marker(pytest.mark.skip(reason=f"{solver} runtime is not installed"))
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
