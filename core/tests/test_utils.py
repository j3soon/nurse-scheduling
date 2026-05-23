"""Unit tests for utility parsing helpers."""

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

import datetime
import os
import sys

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.models import DateRange
from nurse_scheduling import utils


def test_ensure_list_handles_none():
    assert utils.ensure_list(None) == []


def test_parse_dates_rejects_pure_day_when_months_differ():
    date_range = DateRange(startDate=datetime.date(2025, 1, 31), endDate=datetime.date(2025, 2, 2))

    with pytest.raises(ValueError, match="Pure day format"):
        utils.parse_dates("1", {}, date_range)


def test_parse_dates_rejects_month_day_when_years_differ():
    date_range = DateRange(startDate=datetime.date(2024, 12, 31), endDate=datetime.date(2025, 1, 2))

    with pytest.raises(ValueError, match="Pure month-day format"):
        utils.parse_dates("01-01", {}, date_range)


def test_parse_dates_rejects_invalid_date_format():
    date_range = DateRange(startDate=datetime.date(2025, 1, 1), endDate=datetime.date(2025, 1, 10))

    with pytest.raises(ValueError, match="is not in the format"):
        utils.parse_dates("2025/01/01", {}, date_range)


def test_parse_dates_rejects_out_of_range_date():
    date_range = DateRange(startDate=datetime.date(2025, 1, 1), endDate=datetime.date(2025, 1, 10))

    with pytest.raises(ValueError, match="out of the range"):
        utils.parse_dates("2025-01-11", {}, date_range)


def test_parse_sids_rejects_unknown_id():
    with pytest.raises(ValueError, match="Unknown shift type ID"):
        utils.parse_sids(["UNKNOWN"], {"D": [0]})


def test_parse_pids_rejects_unknown_id():
    with pytest.raises(ValueError, match="Unknown person ID"):
        utils.parse_pids(["UNKNOWN"], {"n1": [0]})
