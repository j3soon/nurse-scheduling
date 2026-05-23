"""Helpers for parsing Taiwan MODA holiday calendar CSV files."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
from datetime import datetime

import pandas as pd


# Note that all infer functions are AI generated

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


def _row_date(row):
    return datetime.strptime(str(row["西元日期"]), "%Y%m%d").date()


def _iter_candidate_rows(df, max_distance_days, predicate, include_self=False, row_index=None):
    if row_index is None:
        return []

    origin_row = df.iloc[row_index]
    origin_date = _row_date(origin_row)
    candidates = []
    for candidate_index, candidate_row in df.iterrows():
        if not include_self and candidate_index == row_index:
            continue
        if not predicate(candidate_row):
            continue
        candidate_date = _row_date(candidate_row)
        distance = abs((candidate_date - origin_date).days)
        if distance > max_distance_days:
            continue
        candidates.append((distance, candidate_date, candidate_row["備註"], candidate_index))
    return candidates


def _infer_comp_holiday_source(df, row_index):
    row = df.iloc[row_index]
    if row["備註"] != "補假":
        return None

    row_date = _row_date(row)
    row_block_start = row_index
    while row_block_start > 0 and df.iloc[row_block_start - 1]["備註"] == "補假":
        row_block_start -= 1
    row_block_offset = row_index - row_block_start

    holiday_candidates = _iter_candidate_rows(
        df,
        max_distance_days=7,
        row_index=row_index,
        predicate=lambda candidate_row: (
            candidate_row["是否放假"] == 2
            and pd.notna(candidate_row["備註"])
            and candidate_row["備註"] not in {"補假", "補行上班", "調整放假"}
        ),
    )
    if not holiday_candidates:
        return None

    weekend_candidates = [candidate for candidate in holiday_candidates if candidate[1].weekday() >= 5]
    if weekend_candidates:
        weekend_candidates.sort(key=lambda x: x[1])
        chosen_distance, source_date, source_description, _ = weekend_candidates[
            min(row_block_offset, len(weekend_candidates) - 1)
        ]
        if chosen_distance <= 7:
            return f"補假 ({source_date.isoformat()} {source_description})"

    _, source_date, source_description, _ = min(holiday_candidates, key=lambda x: (x[0], x[1]))
    return f"補假 ({source_date.isoformat()} {source_description})"


def _infer_makeup_workday_source(df, row_index):
    row = df.iloc[row_index]
    if row["備註"] != "補行上班":
        return None

    candidates = _iter_candidate_rows(
        df,
        max_distance_days=21,
        row_index=row_index,
        predicate=lambda candidate_row: candidate_row["備註"] in {"調整放假", "小年夜"},
    )
    if not candidates:
        return None

    _, source_date, source_description, _ = min(candidates, key=lambda x: (x[0], x[1]))
    return f"補行上班 ({source_date.isoformat()} {source_description})"


def _infer_adjusted_off_source(df, row_index):
    row = df.iloc[row_index]
    if row["備註"] != "調整放假":
        return None

    candidates = _iter_candidate_rows(
        df,
        max_distance_days=21,
        row_index=row_index,
        predicate=lambda candidate_row: candidate_row["備註"] == "補行上班",
    )
    if not candidates:
        return None

    _, source_date, source_description, _ = min(candidates, key=lambda x: (x[0], x[1]))
    return f"調整放假 ({source_date.isoformat()} {source_description})"


def _infer_xiaonianye_source(df, row_index):
    row = df.iloc[row_index]
    if row["備註"] != "小年夜":
        return None

    candidates = _iter_candidate_rows(
        df,
        max_distance_days=21,
        row_index=row_index,
        predicate=lambda candidate_row: candidate_row["備註"] == "補行上班",
    )
    if not candidates:
        return None

    _, source_date, source_description, _ = min(candidates, key=lambda x: (x[0], x[1]))
    return f"小年夜 ({source_date.isoformat()} {source_description})"


def _infer_weekend_holiday_makeup_note(df, row_index):
    row = df.iloc[row_index]
    if row["是否放假"] != 2 or pd.isna(row["備註"]):
        return None
    if row["備註"] in {"補假", "補行上班", "調整放假", "小年夜"}:
        return None
    if row["備註"] not in {"開國紀念日", "農曆除夕", "春節"}:
        return None

    row_date = _row_date(row)
    if row_date.weekday() < 5:
        return None

    holiday_block_start = row_index
    while holiday_block_start > 0:
        previous_row = df.iloc[holiday_block_start - 1]
        previous_date = _row_date(previous_row)
        if (
            previous_row["是否放假"] == 2
            and pd.notna(previous_row["備註"])
            and previous_row["備註"] not in {"補假", "補行上班", "調整放假", "小年夜"}
            and previous_date.weekday() >= 5
            and (row_date - previous_date).days <= 2
        ):
            holiday_block_start -= 1
            continue
        break
    holiday_block_offset = row_index - holiday_block_start

    makeup_candidates = _iter_candidate_rows(
        df,
        max_distance_days=7,
        row_index=row_index,
        predicate=lambda candidate_row: candidate_row["備註"] == "補假",
    )
    if not makeup_candidates:
        return None

    makeup_candidates.sort(key=lambda x: x[1])
    _, source_date, source_description, _ = makeup_candidates[min(holiday_block_offset, len(makeup_candidates) - 1)]
    return f"{row['備註']} ({source_date.isoformat()} {source_description})"


def _infer_makeup_holiday_source(df, row_index):
    return (
        _infer_comp_holiday_source(df, row_index)
        or _infer_makeup_workday_source(df, row_index)
        or _infer_adjusted_off_source(df, row_index)
        or _infer_xiaonianye_source(df, row_index)
        or _infer_weekend_holiday_makeup_note(df, row_index)
    )


def parse_special_date_info(csv_file_path):
    df = _read_calendar_csv(csv_file_path)
    df = df[df["備註"].notna()]
    special_date_info = [
        (
            _normalize_date(row["西元日期"]),
            _infer_makeup_holiday_source(df, index) or row["備註"],
            row["是否放假"] == 2,
        )
        for index, row in df.reset_index(drop=True).iterrows()
    ]
    return special_date_info


def format_special_date_info_entry(date, description, is_holiday):
    boolean_literal = "true" if is_holiday else "false"
    return f"  ['{date}', '{description}', {boolean_literal}],"


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
        for date, description, is_holiday in special_date_info:
            print(format_special_date_info_entry(date, description, is_holiday))

if __name__ == "__main__":
    main()
