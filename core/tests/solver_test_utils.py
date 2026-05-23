"""Shared helper utilities for solver truth-table test assertions."""

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

from nurse_scheduling.constants import Operator


def expected_bool_value(operator: Operator, x_value: int, k: int) -> int:
    if operator == Operator.EQ:
        return 1 if x_value == k else 0
    if operator == Operator.NE:
        return 1 if x_value != k else 0
    if operator == Operator.GE:
        return 1 if x_value >= k else 0
    if operator == Operator.GT:
        return 1 if x_value > k else 0
    if operator == Operator.LE:
        return 1 if x_value <= k else 0
    if operator == Operator.LT:
        return 1 if x_value < k else 0
    raise AssertionError(f"Unhandled operator in test: {operator}")
