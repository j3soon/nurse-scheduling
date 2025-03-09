import datetime
import re
import os
from ruamel.yaml import YAML
from typing import Dict, Any
from .models import NurseSchedulingData

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

def is_workday(date: datetime.date) -> bool:
    raise NotImplementedError("is_workday is not implemented yet")

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

def parse_dates(dates, startdate: datetime.date, enddate: datetime.date):
    MAP_KEYWORD_FILTER = {
        'everyday': lambda date: True,
        'weekday': lambda date: date.weekday() < 5,
        'weekend': lambda date: date.weekday() >= 5,
        'workday': is_workday,
        'freeday': lambda date: not is_workday(date)
    }

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
    return parsed_dates

def parse_pids(pids, map_pid_p):
    if isinstance(pids, list):
        # Recursively parse each pid and combine results
        parsed_lists = [parse_pids(pid, map_pid_p) for pid in pids]
        # Flatten and deduplicate
        ps = list(set().union(*parsed_lists))
        return ps
    else:
        # Single pid look up
        return map_pid_p[pids]

def parse_rids(rids, map_rid_r):
    if isinstance(rids, list):
        # Recursively parse each rid and combine results
        parsed_lists = [parse_rids(rid, map_rid_r) for rid in rids]
        # Flatten and deduplicate
        rs = list(set().union(*parsed_lists))
        return rs
    else:
        return map_rid_r[rids]

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
