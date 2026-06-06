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

import ExcelJS from 'exceljs';
import { restorePeopleIdsInXlsx } from '@/utils/restorePeopleIdsInXlsx';

describe('restorePeopleIdsInXlsx', () => {
  it('restores only people IDs in the first worksheet person-header range', async () => {
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Schedule');
    worksheet.getCell('A1').value = 'P1';
    worksheet.getCell('A3').value = 'P1';
    worksheet.getCell('A3').font = { bold: true };
    worksheet.getCell('A4').value = 'P2';
    worksheet.getCell('A5').value = 'P1';
    worksheet.getCell('B3').value = 'P1';
    workbook.addWorksheet('Notes').getCell('A3').value = 'P1';
    const inputBuffer = await workbook.xlsx.writeBuffer();
    const inputBytes = Uint8Array.from(inputBuffer as unknown as ArrayLike<number>);

    const outputBlob = await restorePeopleIdsInXlsx(
      new Blob([inputBytes.buffer]),
      new Map([
        ['P1', 'Alice'],
        ['P2', 'Bob'],
      ]),
      2
    );
    const outputWorkbook = new ExcelJS.Workbook();
    await outputWorkbook.xlsx.load(
      await outputBlob.arrayBuffer() as unknown as Parameters<typeof outputWorkbook.xlsx.load>[0]
    );
    const outputWorksheet = outputWorkbook.getWorksheet('Schedule')!;

    expect(outputWorksheet.getCell('A1').value).toBe('P1');
    expect(outputWorksheet.getCell('A3').value).toBe('Alice');
    expect(outputWorksheet.getCell('A3').font.bold).toBe(true);
    expect(outputWorksheet.getCell('A4').value).toBe('Bob');
    expect(outputWorksheet.getCell('A5').value).toBe('P1');
    expect(outputWorksheet.getCell('B3').value).toBe('P1');
    expect(outputWorkbook.getWorksheet('Notes')!.getCell('A3').value).toBe('P1');
  });
});
