import datetime

# Useful references:
# * [DGPA Work Calendar](https://www.dgpa.gov.tw/informationlist?uid=30)
# * [MODA Open Data](https://data.gov.tw/dataset/14718)
# * [Holidays Python Package (Taiwan)](https://github.com/vacanza/holidays/blob/dev/holidays/countries/taiwan.py)

valid_date_range = (datetime.date(2023, 1, 1), datetime.date(2025, 12, 31))

special_date_info = [
    # 2023
    ('2023-01-01', '開國紀念日 (2023-01-02 補假)', True),
    ('2023-01-02', '補假 (2023-01-01 開國紀念日)', True),
    ('2023-01-07', '補行上班 (2023-01-20 小年夜)', False),
    ('2023-01-20', '小年夜 (2023-01-07 補行上班)', True),
    ('2023-01-21', '農曆除夕 (2023-01-25 補假)', True),
    ('2023-01-22', '春節 (2023-01-26 補假)', True),
    ('2023-01-23', '春節', True),
    ('2023-01-24', '春節', True),
    ('2023-01-25', '補假 (2023-01-21 農曆除夕)', True),
    ('2023-01-26', '補假 (2023-01-22 春節)', True),
    ('2023-01-27', '調整放假 (2023-02-04 補行上班)', True),
    ('2023-02-04', '補行上班 (2023-01-27 調整放假)', False),
    ('2023-02-18', '補行上班 (2023-02-27 調整放假)', False),
    ('2023-02-27', '調整放假 (2023-02-18 補行上班)', True),
    ('2023-02-28', '和平紀念日', True),
    ('2023-03-25', '補行上班 (2023-04-03 調整放假)', False),
    ('2023-04-03', '調整放假 (2023-03-25 補行上班)', True),
    ('2023-04-04', '兒童節', True),
    ('2023-04-05', '民族掃墓節', True),
    ('2023-06-17', '補行上班 (2023-06-23 調整放假)', False),
    ('2023-06-22', '端午節', True),
    ('2023-06-23', '調整放假 (2023-06-17 補行上班)', True),
    ('2023-09-23', '補行上班 (2023-10-09 調整放假)', False),
    ('2023-09-29', '中秋節', True),
    ('2023-10-09', '調整放假 (2023-09-23 補行上班)', True),
    ('2023-10-10', '國慶日', True),
    # 2024
    ('2024-01-01', '開國紀念日', True),
    ('2024-02-08', '小年夜 (2024-02-17 補行上班)', True),
    ('2024-02-09', '農曆除夕', True),
    ('2024-02-10', '春節 (2024-02-13 補假)', True),
    ('2024-02-11', '春節 (2024-02-14 補假)', True),
    ('2024-02-12', '春節', True),
    ('2024-02-13', '補假 (2024-02-10 春節)', True),
    ('2024-02-14', '補假 (2024-02-11 春節)', True),
    ('2024-02-17', '補行上班 (2024-02-08 小年夜)', False),
    ('2024-02-28', '和平紀念日', True),
    ('2024-04-04', '兒童節及民族掃墓節', True),
    ('2024-04-05', '補假 (2024-04-04 兒童節及民族掃墓節)', True),
    ('2024-06-10', '端午節', True),
    ('2024-09-17', '中秋節', True),
    ('2024-10-10', '國慶日', True),
    # 2025
    ('2025-01-01', '開國紀念日', True),
    ('2025-01-27', '小年夜 (2025-02-08 補行上班)', True),
    ('2025-01-28', '農曆除夕', True),
    ('2025-01-29', '春節', True),
    ('2025-01-30', '春節', True),
    ('2025-01-31', '春節', True),
    ('2025-02-08', '補行上班 (2025-01-27 小年夜)', False),
    ('2025-02-28', '和平紀念日', True),
    ('2025-04-03', '補假 (2025-04-04 兒童節及民族掃墓節)', True),
    ('2025-04-04', '兒童節及民族掃墓節', True),
    ('2025-05-30', '補假 (2025-05-31 端午節)', True),
    ('2025-05-31', '端午節', True),
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
        # TODO: What if labor day is on a weekend?
        return True

    # Default to weekday check
    return date.weekday() >= 5
