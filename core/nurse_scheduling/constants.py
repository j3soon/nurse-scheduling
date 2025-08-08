"""Shared constants for the nurse scheduling module."""
from .workdays.taiwan import is_freeday as is_freeday_TW

ALL = 'ALL'  # For dates, shift types, and people
OFF = 'OFF'  # For shift types
OFF_sid = -1  # For shift types
INF = 'INF'  # For weights
NINF = '-INF'  # For weights 

MAP_WEEKDAY_TO_STR = [
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
    'sunday',
]
MAP_DATE_KEYWORD_TO_FILTER = {
    ALL: lambda date: True,
    'everyday': lambda date: True,
    'weekday': lambda date: date.weekday() < 5,
    'weekend': lambda date: date.weekday() >= 5,
    'workday': lambda date: not is_freeday_TW(date),
    'freeday': is_freeday_TW,
    'workday(labor)': lambda date: not is_freeday_TW(date, True),
    'freeday(labor)': lambda date: is_freeday_TW(date, True),
}
