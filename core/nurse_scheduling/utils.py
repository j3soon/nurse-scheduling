import datetime
import re
import os
from ruamel.yaml import YAML
from typing import Dict, Any
from .models import NurseSchedulingData
from .workdays.taiwan import is_freeday as is_freeday_TW

yaml = YAML(typ='safe')

MAP_WEEKDAY_STR = [
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
    'sunday',
]

def ensure_list(val):
    if val is None:
        return []
    return [val] if not isinstance(val, list) else val

def ortools_expression_to_bool_var(
        model, varname, true_expression, false_expression
    ):
    # Ref: https://stackoverflow.com/a/70571397
    var = model.NewBoolVar(varname)
    model.Add(true_expression).OnlyEnforceIf(var)
    model.Add(false_expression).OnlyEnforceIf(var.Not())
    return var

def _parse_single_date(date: str, startdate: datetime.date, enddate: datetime.date):
    error_details = f'- Start date: {startdate}\n- End date: {enddate}\n'
    if match := re.match(r'^\d{1,2}$', date):
        if startdate.year != enddate.year or startdate.month != enddate.month:
            raise ValueError(f'Pure day format (D) is not allowed when start date and end date are not in the same month.\n{error_details}')
        return datetime.date(startdate.year, startdate.month, int(match.group(0)))
    elif match := re.match(r'^(\d{2})-(\d{2})$', date):
        if startdate.year != enddate.year:
            raise ValueError(f'Pure month-day format (MM-DD) is not allowed when start date and end date are not in the same year.\n{error_details}')
        return datetime.date(startdate.year, *map(int, match.groups()))
    elif match := re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date):
        return datetime.date(*map(int, match.groups()))
    raise ValueError(f"Date '{date}' is not in the format of YYYY-MM-DD, MM-DD, or D.\n{error_details}")

def parse_dates(dates, startdate: datetime.date, enddate: datetime.date, country: str):
    MAP_KEYWORD_FILTER = {
        'everyday': lambda date: True,
        'weekday': lambda date: date.weekday() < 5,
        'weekend': lambda date: date.weekday() >= 5,
        'workday': lambda date: not is_freeday_TW(date),
        'freeday': is_freeday_TW,
        'workday(labor)': lambda date: not is_freeday_TW(date, True),
        'freeday(labor)': lambda date: is_freeday_TW(date, True),
    }

    if country is not None and country != 'TW':
        raise ValueError(f"Country {country} is not supported yet")

    dates = map(str, ensure_list(dates))
    n_days = (enddate - startdate).days + 1
    dates_in_timespan = [startdate + datetime.timedelta(days=i) for i in range(n_days)]
    parsed_dates = []

    for date_str in dates:
        if date_str in MAP_KEYWORD_FILTER:
            parsed_dates += filter(MAP_KEYWORD_FILTER[date_str], dates_in_timespan)
        elif date_str in MAP_WEEKDAY_STR:
            weekday_index = MAP_WEEKDAY_STR.index(date_str)
            parsed_dates += [date for date in dates_in_timespan if date.weekday() == weekday_index]
        elif match := re.match(r'^([\d-]+)~([\d-]+)$', date_str):
            startdate = _parse_single_date(match.group(1), startdate, enddate)
            enddate = _parse_single_date(match.group(2), startdate, enddate)
            parsed_dates += [
                startdate + datetime.timedelta(days=i)
                for i in range((enddate - startdate).days + 1)
            ]
        else:
            parsed_dates.append(_parse_single_date(date_str, startdate, enddate))

    result = []
    for date in parsed_dates:
        if date < startdate or date > enddate:
            raise ValueError(f"Date '{date}' is out of the range of start date and end date.")
        result.append((date - startdate).days)

    return result

def parse_sids(sids, map_sid_s):
    sids = ensure_list(sids)
    result = []
    for sid in sids:
        if sid not in map_sid_s:
            raise ValueError(f"Unknown shift type ID: {sid}")
        result.extend(map_sid_s[sid])
    return result

def parse_pids(pids, map_pid_p):
    pids = ensure_list(pids)
    result = []
    for pid in pids:
        if pid not in map_pid_p:
            raise ValueError(f"Unknown person ID: {pid}")
        result.extend(map_pid_p[pid])
    return result

def _load_yaml(filepath: str) -> Dict[str, Any]:
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File {filepath} should exist")
    with open(filepath, "r") as r:
        # Use ruamel.yaml instead of PyYAML to support YAML 1.2
        # This avoids the auto-conversion of special strings such as
        # `Off` into boolean value `False`.
        return yaml.load(r)

def load_data(filepath: str) -> NurseSchedulingData:
    """Load nurse scheduling data from a YAML file.
    
    Args:
        filepath: Path to the YAML file
    
    Returns:
        NurseSchedulingData: The validated scheduling data
    """
    data = _load_yaml(filepath)
    return NurseSchedulingData(**data)
