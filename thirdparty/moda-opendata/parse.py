import os
from datetime import datetime

import pandas as pd


def _read_calendar_csv(csv_file_path):
    last_error = None
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            return pd.read_csv(csv_file_path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError(
        getattr(last_error, "encoding", "unknown"),
        getattr(last_error, "object", b""),
        getattr(last_error, "start", 0),
        getattr(last_error, "end", 0),
        f"Unable to decode {csv_file_path} with utf-8-sig/cp950/big5",
    )


def _normalize_date(value):
    return datetime.strptime(str(value), "%Y%m%d").date().isoformat()


def parse_special_date_info(csv_file_path):
    df = _read_calendar_csv(csv_file_path)
    df = df[df["備註"].notna()]
    special_date_info = [
        (_normalize_date(date), description, is_holiday == 2)
        for date, description, is_holiday in zip(df["西元日期"], df["備註"], df["是否放假"], strict=False)
    ]
    return special_date_info


def main():
    filenames = [
        "112年中華民國政府行政機關辦公日曆表.csv",
        "113年中華民國政府行政機關辦公日曆表.csv",
        "114年中華民國政府行政機關辦公日曆表(1141020更新).csv",
        "115年中華民國政府行政機關辦公日曆表.csv",
    ]
    for filename in filenames:
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Construct the path to the CSV file
        csv_file_path = os.path.join(script_dir, filename)
        # Parse the holiday calendar
        special_date_info = parse_special_date_info(csv_file_path)

        # Print the results
        print(f"Found {len(special_date_info)} special date entries:")
        for date, description, is_holiday in special_date_info:
            print(f"('{date}', '{description}', {is_holiday}),")

if __name__ == "__main__":
    main()
