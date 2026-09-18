"""Print bounded, sheet-aware content from an XLSX workbook."""

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

# This code is mostly AI generated.

import argparse
import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.xml.functions import DEFUSEDXML

MAX_ARCHIVE_ENTRIES = 1_000
MAX_UNCOMPRESSED_BYTES = 50_000_000
MAX_SHEETS = 20

if not DEFUSEDXML:
    raise RuntimeError("defusedxml is required for untrusted XLSX files")


def _check_archive(path: Path) -> None:
    """Reject oversized or malformed workbook archives before XML parsing."""
    with path.open("rb") as stream:
        signature = stream.read(4)
    if signature != b"PK\x03\x04":
        raise ValueError("Not an XLSX archive")
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("XLSX archive has too many entries")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise ValueError("Encrypted XLSX files are not supported")
            if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("XLSX archive expands beyond the allowed size")
            names = {entry.filename for entry in entries}
            if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
                raise ValueError("Not an XLSX workbook")
    except BadZipFile as exc:
        raise ValueError("Invalid XLSX archive") from exc


def inspect_workbook(
    path: Path,
    *,
    sheet_name: str | None = None,
    start_row: int = 1,
    start_column: int = 1,
    max_rows: int = 200,
    max_columns: int = 50,
) -> dict[str, Any]:
    """Return bounded cells with both formulas and last-saved cached values."""
    if min(start_row, start_column, max_rows, max_columns) <= 0:
        raise ValueError("Row and column positions and limits must be positive")
    if max_rows * max_columns > 10_000:
        raise ValueError("Select at most 10,000 cells per sheet")
    _check_archive(path)
    formula_book = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        cached_book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    except Exception:
        formula_book.close()
        raise
    try:
        available = formula_book.sheetnames
        if sheet_name is not None and sheet_name not in available:
            raise ValueError(f"Unknown sheet {sheet_name!r}. Available sheets: {available}")
        selected = [sheet_name] if sheet_name is not None else available[:MAX_SHEETS]
        sheets = []
        for name in selected:
            worksheet = formula_book[name]
            cached_sheet = cached_book[name]
            rows = []
            formula_rows = worksheet.iter_rows(
                min_row=start_row,
                max_row=start_row + max_rows - 1,
                min_col=start_column,
                max_col=start_column + max_columns - 1,
            )
            cached_rows = cached_sheet.iter_rows(
                min_row=start_row,
                max_row=start_row + max_rows - 1,
                min_col=start_column,
                max_col=start_column + max_columns - 1,
            )
            for row_number, (formula_row, cached_row) in enumerate(
                zip(formula_rows, cached_rows, strict=True), start=start_row
            ):
                values = []
                for formula_cell, cached_cell in zip(formula_row, cached_row, strict=True):
                    value = formula_cell.value
                    if formula_cell.data_type == "f":
                        values.append(
                            {
                                "cell": formula_cell.coordinate,
                                "formula": getattr(value, "text", value),
                                "cached_value": cached_cell.value,
                            }
                        )
                    else:
                        values.append(value)
                while values and values[-1] is None:
                    values.pop()
                if values:
                    rows.append({"row": row_number, "values": values})
            sheets.append(
                {
                    "name": name,
                    "state": worksheet.sheet_state,
                    "reported_rows": worksheet.max_row,
                    "reported_columns": worksheet.max_column,
                    "first_column": start_column,
                    "rows": rows,
                    "truncated": (
                        start_row > 1
                        or start_column > 1
                        or (worksheet.max_row or 0) > start_row + max_rows - 1
                        or (worksheet.max_column or 0) > start_column + max_columns - 1
                    ),
                }
            )
        return {
            "path": str(path),
            "sheet_names": available,
            "sheets_truncated": sheet_name is None and len(available) > MAX_SHEETS,
            "cached_values_are_last_saved_not_recalculated": True,
            "sheets": sheets,
        }
    finally:
        formula_book.close()
        cached_book.close()


def main() -> None:
    """Run the workbook inspector from the sandbox shell."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--sheet")
    parser.add_argument("--start-row", type=int, default=1)
    parser.add_argument("--start-column", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=200)
    parser.add_argument("--max-columns", type=int, default=50)
    args = parser.parse_args()
    result = inspect_workbook(
        args.path,
        sheet_name=args.sheet,
        start_row=args.start_row,
        start_column=args.start_column,
        max_rows=args.max_rows,
        max_columns=args.max_columns,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
