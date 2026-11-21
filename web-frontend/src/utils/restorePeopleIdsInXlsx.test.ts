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
import JSZip from 'jszip';
import { restorePeopleIdsInXlsx } from '@/utils/restorePeopleIdsInXlsx';

describe('restorePeopleIdsInXlsx', () => {
  it('restores only people IDs in the first worksheet person-header range', async () => {
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Schedule');
    worksheet.getColumn(1).width = 10;
    worksheet.pageSetup = {
      paperSize: 9,
      orientation: 'landscape',
      fitToPage: true,
      fitToWidth: 1,
      fitToHeight: 0,
      printArea: 'A1:B5',
      printTitlesRow: '1:2',
    };
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
        ['P1', '陳小華測試姓名'],
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
    expect(outputWorksheet.getCell('A3').value).toBe('陳小華測試姓名');
    expect(outputWorksheet.getCell('A3').font.bold).toBe(true);
    expect(outputWorksheet.getCell('A4').value).toBe('Bob');
    expect(outputWorksheet.getCell('A5').value).toBe('P1');
    expect(outputWorksheet.getCell('B3').value).toBe('P1');
    expect(outputWorksheet.getColumn(1).width).toBeGreaterThanOrEqual(16);
    expect(outputWorksheet.pageSetup).toMatchObject(worksheet.pageSetup);
    expect(outputWorkbook.getWorksheet('Notes')!.getCell('A3').value).toBe('P1');
  });

  it('keeps the backend print definitions and worksheet property order when restoring inline names', async () => {
    const workbook = new ExcelJS.Workbook();
    workbook.addWorksheet('Schedule');
    const notes = workbook.addWorksheet('Notes');
    notes.getCell('A1').value = 'Request notes';
    notes.autoFilter = 'A1:C1';
    const inputBuffer = await workbook.xlsx.writeBuffer();
    const original = await JSZip.loadAsync(inputBuffer);
    const schedulePart = 'xl/worksheets/sheet1.xml';
    const namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
    const sheetProperties = '<sheetPr><outlinePr summaryBelow="1" /><pageSetUpPr fitToPage="1" /></sheetPr>';
    original.file(schedulePart, `
      <worksheet xmlns="${namespace}">
        ${sheetProperties}
        <cols><col min="1" max="1" width="10" customWidth="1" /><col min="2" max="2" width="4.5" /></cols>
        <sheetData><row r="3"><c r="A3" t="inlineStr"><is><t>P1</t></is></c></row></sheetData>
        <pageMargins left="0.197" right="0.197" top="0.197" bottom="0.197" header="0.5" footer="0.5" />
        <pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0" />
      </worksheet>`);
    const workbookPart = 'xl/workbook.xml';
    const workbookXml = (await original.file(workbookPart)!.async('string')).replace(
      '</workbook>',
      `<definedNames>
        <definedName name="_xlnm.Print_Titles" localSheetId="0">'Schedule'!$1:$2</definedName>
        <definedName name="_xlnm.Print_Area" localSheetId="0">'Schedule'!$A$1:$AF$5</definedName>
        <definedName name="_xlnm._FilterDatabase" localSheetId="1" hidden="1">'Notes'!$A$1:$C$1</definedName>
      </definedNames></workbook>`
    );
    original.file(workbookPart, workbookXml);
    const blob = new Blob([await original.generateAsync({ type: 'arraybuffer' })]);

    const restored = await restorePeopleIdsInXlsx(blob, new Map([['P1', ' =林<&>_x0008_\r\b ']]), 1);
    const output = await JSZip.loadAsync(await restored.arrayBuffer());
    const xml = await output.file(schedulePart)!.async('string');
    const sheet = new DOMParser().parseFromString(xml, 'application/xml');
    expect(Array.from(sheet.querySelector('sheetPr')!.children, child => child.localName))
      .toEqual(['outlinePr', 'pageSetUpPr']);
    expect(Object.keys(output.files).filter(path => !output.files[path].dir).sort())
      .toEqual(Object.keys(original.files).filter(path => !original.files[path].dir).sort());
    for (const [path, file] of Object.entries(original.files)) {
      if (!file.dir && path !== schedulePart) {
        expect(await output.file(path)?.async('uint8array'), path).toEqual(await file.async('uint8array'));
      }
    }

    expect(sheet.querySelector('pageSetup')?.getAttribute('fitToHeight')).toBe('0');
    expect(sheet.querySelector('pageMargins')?.getAttribute('left')).toBe('0.197');
    expect(sheet.querySelector('col[min="2"]')?.getAttribute('width')).toBe('4.5');
    const cell = sheet.querySelector('c[r="A3"]');
    expect(cell?.getAttribute('t')).toBe('inlineStr');
    expect(cell?.querySelector('f')).toBeNull();
    expect(cell?.querySelector('t')?.getAttribute('xml:space')).toBe('preserve');
    expect(cell?.querySelector('t')?.textContent).toBe(' =林<&>_x005F_x0008__x000D__x0008_ ');
  });
});
