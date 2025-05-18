import datetime
import re
from .workdays.taiwan import is_freeday as is_freeday_TW

MAP_WEEKDAY_STR = [
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
    'sunday',
]

ALL = 'ALL' # For dates, shift types, and people
OFF = 'OFF' # For shift types
OFF_sid = -1 # For shift types
INF = 'INF' # For weights
NINF = '-INF' # For weights

def ensure_list(val):
    if val is None:
        return []
    return [val] if not isinstance(val, list) else val

def ortools_expression_to_bool_var(
        model, varname, true_expression, false_expression
    ):
    # Ref: https://stackoverflow.com/a/70571397
    # Ref: https://github.com/google/or-tools/blob/master/ortools/sat/docs/channeling.md
    var = model.NewBoolVar(varname)
    model.Add(true_expression).OnlyEnforceIf(var)
    model.Add(false_expression).OnlyEnforceIf(var.Not())
    return var

def add_objective(ctx, weight, expression):
    if weight == INF:
        ctx.model.Add(expression == 1)
    elif weight == NINF:
        ctx.model.Add(expression == 0)
    else:
        ctx.objective += weight * expression

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
        ALL: lambda date: True,
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

    return sorted(set(result))

def parse_sids(sids, map_sid_s):
    sids = ensure_list(sids)
    result = []
    for sid in sids:
        if sid not in map_sid_s:
            raise ValueError(f"Unknown shift type ID: {sid}")
        result.extend(map_sid_s[sid])
    return sorted(set(result))

def parse_pids(pids, map_pid_p):
    pids = ensure_list(pids)
    result = []
    for pid in pids:
        if pid not in map_pid_p:
            raise ValueError(f"Unknown person ID: {pid}")
        result.extend(map_pid_p[pid])
    return sorted(set(result))

def is_ss_equivalent_to_all(ss, n_shift_types):
    return set(ss) == set(range(n_shift_types))
