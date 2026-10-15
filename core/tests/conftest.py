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

from functools import cache

import pytest

from nurse_scheduling.server.solver_options import solver_is_available


def pytest_addoption(parser):
    parser.addoption(
        "--skip-unavailable-solvers",
        action="store_true",
        help="Skip tests marked requires_solver when that optional solver runtime is not installed.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_solver(solver): the test needs this optional solver runtime")


def pytest_collection_modifyitems(config, items):
    # Without the option, a missing runtime fails its tests, so CI cannot pass with an incomplete install.
    if not config.getoption("--skip-unavailable-solvers"):
        return
    available = cache(solver_is_available)
    for item in items:
        for marker in item.iter_markers("requires_solver"):
            solver = marker.args[0]
            if not available(solver):
                item.add_marker(pytest.mark.skip(reason=f"{solver} runtime is not installed"))
