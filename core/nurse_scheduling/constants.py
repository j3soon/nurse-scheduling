"""Shared constants for the nurse scheduling module."""
from .workdays.taiwan import is_freeday as is_freeday_TW

ALL = 'ALL'  # For dates, shift types, and people
OFF = 'OFF'  # For shift types
OFF_sid = -1  # For shift types
INF = 'INF'  # For weights
NINF = '-INF'  # For weights 

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
