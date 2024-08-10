import datetime
import re


def ensure_list(val):
    if val is None:
        return []
    return [val] if not isinstance(val, list) else val

def required_n_people(requirement):
    if not isinstance(requirement.required_people, int):
        raise NotImplementedError("required_people with type other than int is not supported yet")
    return requirement.required_people

def ortools_expression_to_bool_var(
        model, varname, true_expression, false_expression
    ):
    # Ref: https://stackoverflow.com/a/70571397
    var = model.NewBoolVar(varname)
    model.Add(true_expression).OnlyEnforceIf(var)
    model.Add(false_expression).OnlyEnforceIf(var.Not())
    return var

def parse_dates(dates, startdate: datetime.date, enddate: datetime.date):
    dates = map(str, ensure_list(dates))
    parsed_dates = []
    for date in dates:
        error_details = f'Day: {date}\nStart date: {startdate}\nEnd date: {enddate}\n'
        if match := re.match(r'^\d{1,2}$', date):
            if startdate.year != enddate.year or startdate.month != enddate.month:
                raise ValueError(f'Pure day format (D) is not allowed when start date and end date are not in the same month.\n{error_details}')
            parsed_date = datetime.date(startdate.year, startdate.month, int(match.group(0)))
        elif match := re.match(r'^(\d{2})-(\d{2})$', date):
            if startdate.year != enddate.year:
                raise ValueError(f'Pure month-day format (MM-DD) is not allowed when start date and end date are not in the same year.\n{error_details}')
            parsed_date = datetime.date(startdate.year, *map(int, match.groups()))
        elif match := re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date):
            parsed_date = datetime.date(*map(int, match.groups()))
        else:
            raise ValueError(f'Date is not in the format of YYYY-MM-DD, MM-DD, or D.\n{error_details}')
        parsed_dates.append(parsed_date)
    return parsed_dates
