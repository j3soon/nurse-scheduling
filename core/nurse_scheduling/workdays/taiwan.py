import datetime

# Useful references:
# * [DGPA Work Calendar](https://www.dgpa.gov.tw/informationlist?uid=30)
# * [MODA Open Data](https://data.gov.tw/dataset/14718)
# * [Holidays Python Package (Taiwan)](https://github.com/vacanza/holidays/blob/dev/holidays/countries/taiwan.py)

valid_date_range = (datetime.date(2025, 1, 1), datetime.date(2025, 12, 31))

special_date_info = [
    ('2025-01-01', '開國紀念日', True),
    ('2025-01-27', '彈性放假（小年夜）', True),
    ('2025-01-28', '農曆除夕', True),
    ('2025-01-29', '春節', True),
    ('2025-01-30', '春節', True),
    ('2025-01-31', '春節', True),
    ('2025-02-08', '補行上班（小年夜）', False),
    ('2025-02-28', '和平紀念日', True),
    ('2025-04-03', '補假（兒童節及民族掃墓節）', True),
    ('2025-04-04', '兒童節及民族掃墓節', True),
    ('2025-05-30', '補假（端午節）', True),
    ('2025-10-06', '中秋節', True),
    ('2025-10-10', '國慶日', True),
]

def is_freeday(date: datetime.date, is_labor: bool = False) -> bool:
    # Check if date is in valid range
    if not (valid_date_range[0] <= date <= valid_date_range[1]):
        raise ValueError(f"Date {date} is outside valid range {valid_date_range}")

    # Check special dates first
    for date_str, reason, is_freeday in special_date_info:
        if date_str == date.strftime('%Y-%m-%d'):
            return is_freeday

    # Deal with labor day
    if is_labor and date == datetime.date(2025, 5, 1):
            return True

    # Default to weekday check
    return date.weekday() >= 5
