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

// This test is mostly AI generated.

import { execFile } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import ExcelJS from 'exceljs';
import JSZip from 'jszip';
import { restorePeopleIdsInXlsx } from './fixtures/restorePeopleIdsInXlsx.v0.2.0';
import { expect, test } from './test';

const execFileAsync = promisify(execFile);

const scheduleSpec = `
apiVersion: alpha
dates:
  range: {startDate: 2026-12-01, endDate: 2026-12-31}
people:
  items: [{id: P1, history: [D, D, D, D, D]}]
shiftTypes:
  items: [{id: D}]
preferences:
  - {type: at most one shift per day}
  - {type: shift type requirement, shiftType: D, date: ["01", "02", "31"], requiredNumPeople: 1}
  - {type: shift request, person: P1, date: "01", shiftType: OFF, weight: 5}
export:
  formatting:
    - type: cell
      people: [ALL]
      dates: [ALL]
      shiftTypes: [ALL, OFF]
      note: {text: Unmet request}
      when:
        preference: {types: [shift request], requestShape: [person-item-to-date-item], satisfied: false}
`;

test('the v0.2.0 exporter restores names in a printable schedule with Notes', async () => {
  test.setTimeout(60_000);
  const inputPath = test.info().outputPath('schedule-spec.yaml');
  const xlsxPath = test.info().outputPath('schedule.xlsx');
  await mkdir(path.dirname(inputPath), { recursive: true });
  await writeFile(inputPath, scheduleSpec);
  await execFileAsync(process.env.AI_EXPORT_PYTHON ?? 'python', [
    '-m', 'nurse_scheduling.cli', inputPath, xlsxPath, '--prettify', '--solver', 'ortools/cp-sat',
  ], {
    cwd: path.resolve(__dirname, '../../core'),
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    timeout: 45_000,
  });

  const source = new Blob([new Uint8Array(await readFile(xlsxPath))]);
  const name = '林小華楊';
  const restored = await restorePeopleIdsInXlsx(source, new Map([['P1', name]]), 1);
  const bytes = await restored.arrayBuffer();

  const zip = await JSZip.loadAsync(bytes);
  const sheetXml = await zip.file('xl/worksheets/sheet1.xml')!.async('string');
  const sheetProperties = sheetXml.match(/<sheetPr>(.*?)<\/sheetPr>/s)?.[1];
  // ExcelJS reverses the required order if outlinePr and pageSetUpPr are both present.
  expect(sheetProperties).toBe('<pageSetUpPr fitToPage="1"/>');

  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(bytes as unknown as Parameters<typeof workbook.xlsx.load>[0]);
  const sheet = workbook.worksheets[0];
  expect(sheet.getCell('A3').value).toBe(name);
  expect(sheet.getCell('AG1').value).toBe(31);
  expect(sheet.pageSetup).toMatchObject({
    paperSize: 9,
    orientation: 'landscape',
    fitToPage: true,
    fitToWidth: 1,
    fitToHeight: 0,
    printTitlesRow: '1:2',
  });
  expect(sheet.pageSetup.printArea).toMatch(/^A1:AG\d+$/);
  const notes = workbook.getWorksheet('Notes');
  expect(notes?.getCell('C2').value).toBe('Unmet request');
  expect(sheet.getCell('C3').hyperlink).toBe("#'Notes'!A2");
  expect(notes?.getCell('A2').hyperlink).toBe("#'Sheet1'!C3");
});
