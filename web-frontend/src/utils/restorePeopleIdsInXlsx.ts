/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// Restore anonymized people IDs in an XLSX workbook before browser download.
import ExcelJS from 'exceljs';

const XLSX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

export async function restorePeopleIdsInXlsx(
  xlsxBlob: Blob,
  originalIdByAnonymizedId: ReadonlyMap<string, string>,
  peopleCount: number
): Promise<Blob> {
  const workbook = new ExcelJS.Workbook();
  const arrayBuffer = await xlsxBlob.arrayBuffer();
  await workbook.xlsx.load(arrayBuffer as unknown as Parameters<typeof workbook.xlsx.load>[0]);

  const scheduleWorksheet = workbook.worksheets[0];
  let restoredNameWidth = 0;
  for (let row = 3; row < 3 + peopleCount; row += 1) {
    const cell = scheduleWorksheet.getCell(row, 1);
    if (typeof cell.value !== 'string') {
      continue;
    }
    const originalId = originalIdByAnonymizedId.get(cell.value);
    if (originalId !== undefined) {
      cell.value = originalId;
      for (const line of originalId.split(/\r?\n/)) {
        // Estimate wide glyphs in units of the default font's digit width.
        let width = 2;
        for (const ch of line) {
          width += /[MWmw]|[^ -~]/.test(ch) ? 2 : 1;
        }
        restoredNameWidth = Math.max(restoredNameWidth, width);
      }
    }
  }

  if (scheduleWorksheet.pageSetup.fitToPage && restoredNameWidth > 0) {
    const names = scheduleWorksheet.getColumn(1);
    names.width = Math.max(names.width ?? 9, Math.min(restoredNameWidth, 255));
  }

  const outputBuffer = await workbook.xlsx.writeBuffer();
  const outputBytes = Uint8Array.from(outputBuffer as unknown as ArrayLike<number>);
  return new Blob([outputBytes.buffer], { type: XLSX_MIME_TYPE });
}
