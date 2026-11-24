"""Utility helpers used across parsing, modeling, and reporting."""

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

import datetime
import math
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from .errors import InputValidationError

if TYPE_CHECKING:
    from .models import DateRange


def ensure_list(val):
    if val is None:
        return []
    return [val] if not isinstance(val, list) else val


def add_objective(ctx, weight, expression):
    """
    Add an objective term with the given weight.

    Args:
        ctx: Context object
        weight: Weight for the objective term (can be inf/-inf for hard constraints)
        expression: Expression to add to objective
    """
    if weight == math.inf:
        ctx.solver.add_constraint(expression == 1)
    elif weight == -math.inf:
        ctx.solver.add_constraint(expression == 0)
    else:
        ctx.objective += weight * expression


_DAY_DATE_PATTERN = r"^\d{1,2}$"
_MONTH_DAY_DATE_PATTERN = r"^(\d{2})-(\d{2})$"
_ISO_DATE_PATTERN = r"^(\d{4})-(\d{2})-(\d{2})$"
_DATE_RANGE_PATTERN = r"^([\d-]+)~([\d-]+)$"
DATE_RANGE_SELECTOR_PATTERN = re.compile(_DATE_RANGE_PATTERN, re.ASCII)


def is_date_selector_shape(value: str) -> bool:
    """Reserve date-shaped names, including spellings with non-ASCII digits."""
    patterns = (_DAY_DATE_PATTERN, _MONTH_DAY_DATE_PATTERN, _ISO_DATE_PATTERN, _DATE_RANGE_PATTERN)
    return any(re.match(pattern, value) for pattern in patterns)


def _parse_single_date(date: str, date_range: "DateRange") -> datetime.date:
    startdate, enddate = date_range.startDate, date_range.endDate
    error_details = f"- Start date: {startdate}\n- End date: {enddate}\n"
    if match := re.match(_DAY_DATE_PATTERN, date, re.ASCII):
        if startdate.year != enddate.year or startdate.month != enddate.month:
            raise InputValidationError(
                f"Pure day format (D) is not allowed when start date and end date are not in the same month.\n{error_details}"
            )
        return datetime.date(startdate.year, startdate.month, int(match.group(0)))
    elif match := re.match(_MONTH_DAY_DATE_PATTERN, date, re.ASCII):
        if startdate.year != enddate.year:
            raise InputValidationError(
                f"Pure month-day format (MM-DD) is not allowed when start date and end date are not in the same year.\n{error_details}"
            )
        return datetime.date(startdate.year, *map(int, match.groups()))
    elif match := re.match(_ISO_DATE_PATTERN, date, re.ASCII):
        return datetime.date(*map(int, match.groups()))
    raise InputValidationError(f"Date '{date}' is not in the format of YYYY-MM-DD, MM-DD, or D.\n{error_details}")


def parse_dates(dates, map_did_d: Mapping[str, tuple[int, ...]], date_range: "DateRange") -> list[int]:
    startdate, enddate = date_range.startDate, date_range.endDate
    dates = map(str, ensure_list(dates))
    parsed_dates = []

    for date_str in dates:
        if date_str in map_did_d:
            parsed_dates += [startdate + datetime.timedelta(days=i) for i in map_did_d[date_str]]
        elif match := DATE_RANGE_SELECTOR_PATTERN.match(date_str):
            range_start = _parse_single_date(match.group(1), date_range)
            range_end = _parse_single_date(match.group(2), date_range)
            parsed_dates += [
                range_start + datetime.timedelta(days=i) for i in range((range_end - range_start).days + 1)
            ]
        else:
            parsed_dates.append(_parse_single_date(date_str, date_range))

    result = []
    for date in parsed_dates:
        if date < startdate or date > enddate:
            raise InputValidationError(f"Date '{date}' is out of the range of start date and end date.")
        result.append((date - startdate).days)

    return sorted(set(result))


def parse_sids(sids, map_sid_s):
    sids = ensure_list(sids)
    result = []
    for sid in sids:
        # Look up by string, matching how the ID maps are keyed.
        if str(sid) not in map_sid_s:
            raise InputValidationError(f"Unknown shift type ID: {sid}")
        result.extend(map_sid_s[str(sid)])
    return sorted(set(result))


def parse_pids(pids, map_pid_p):
    pids = ensure_list(pids)
    result = []
    for pid in pids:
        if str(pid) not in map_pid_p:
            raise InputValidationError(f"Unknown person ID: {pid}")
        result.extend(map_pid_p[str(pid)])
    return sorted(set(result))


def is_ss_equivalent_to_all(ss, n_shift_types):
    return set(ss) == set(range(n_shift_types))
