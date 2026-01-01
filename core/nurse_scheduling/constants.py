"""
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.

Copyright (C) 2023-2026 Johnson Sun

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# Shared constants for the nurse scheduling module.

from .workdays.taiwan import is_freeday as is_freeday_TW

ALL = 'ALL'  # For dates, shift types, and people
OFF = 'OFF'  # For shift types
OFF_sid = -1  # For shift types

MAP_WEEKDAY_TO_STR = [
    'MONDAY',
    'TUESDAY',
    'WEDNESDAY',
    'THURSDAY',
    'FRIDAY',
    'SATURDAY',
    'SUNDAY',
]
MAP_DATE_KEYWORD_TO_FILTER = {
    ALL: lambda date: True,
    'WEEKDAY': lambda date: date.weekday() < 5,
    'WEEKEND': lambda date: date.weekday() >= 5,
    'WORKDAY': lambda date: not is_freeday_TW(date),
    'FREEDAY': is_freeday_TW,
    'WORKDAY(LABOR)': lambda date: not is_freeday_TW(date, True),
    'FREEDAY(LABOR)': lambda date: is_freeday_TW(date, True),
}
