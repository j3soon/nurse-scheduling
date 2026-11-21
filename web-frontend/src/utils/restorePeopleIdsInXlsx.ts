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
import JSZip from 'jszip';

const XLSX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const RELATIONSHIP_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const XML_NS = 'http://www.w3.org/XML/1998/namespace';
const PACKAGE_ROOT = 'https://xlsx.invalid/';

async function readXmlPart(zip: JSZip, path: string): Promise<Document> {
  const file = zip.file(path);
  if (!file) {
    throw new Error(`Missing XLSX part: ${path}`);
  }
  const document = new DOMParser().parseFromString(await file.async('string'), 'application/xml');
  if (document.documentElement.localName === 'parsererror') {
    throw new Error(`Invalid XLSX XML: ${path}`);
  }
  return document;
}

async function readRelationships(zip: JSZip, partPath: string): Promise<Element[]> {
  const directoryEnd = partPath.lastIndexOf('/') + 1;
  const path = `${partPath.slice(0, directoryEnd)}_rels/${partPath.slice(directoryEnd)}.rels`;
  return Array.from((await readXmlPart(zip, path)).documentElement.children);
}

function partTarget(partPath: string, relationship?: Element): string | undefined {
  const target = relationship?.getAttribute('Target');
  if (target && relationship?.getAttribute('TargetMode') !== 'External') {
    const url = new URL(target, PACKAGE_ROOT + partPath);
    if (url.href.startsWith(PACKAGE_ROOT)) {
      return url.pathname.slice(1);
    }
  }
}

function spreadsheetText(container: Element | undefined): string | undefined {
  if (container) {
    const text = container.getElementsByTagNameNS(container.namespaceURI, 't');
    return Array.from(text, element => element.textContent).join('');
  }
}

function escapeSpreadsheetText(text: string): string {
  // Escape literal XLSX escape sequences before encoding characters that XML cannot store.
  const escaped = text.replace(/_(?=x[0-9a-f]{4}_)/gi, '_x005F_');
  return escaped.replace(/[\x00-\x08\x0b-\x1f\ud800-\udfff\ufffe\uffff]/gu, character => {
    const hex = character.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0');
    return `_x${hex}_`;
  });
}

export async function restorePeopleIdsInXlsx(
  xlsxBlob: Blob,
  originalIdByAnonymizedId: ReadonlyMap<string, string>,
  peopleCount: number
): Promise<Blob> {
  if (originalIdByAnonymizedId.size === 0 || peopleCount === 0) {
    return xlsxBlob;
  }

  // Keep the backend's workbook, including its named ranges and print settings.
  // ExcelJS rewrites sheetPr children out of order when fit-to-page is enabled.
  const zip = await JSZip.loadAsync(await xlsxBlob.arrayBuffer());
  const packageRelationships = await readRelationships(zip, '');
  const workbookPath = partTarget('', packageRelationships.find(
    relation => relation.getAttribute('Type') === `${RELATIONSHIP_NS}/officeDocument`
  ));
  if (!workbookPath) {
    throw new Error('Missing XLSX workbook');
  }
  const workbook = await readXmlPart(zip, workbookPath);
  const namespace = workbook.documentElement.namespaceURI;
  const sheetId = workbook.getElementsByTagNameNS(namespace, 'sheet')[0]?.getAttributeNS(RELATIONSHIP_NS, 'id');
  const relationships = await readRelationships(zip, workbookPath);
  const sheetPath = partTarget(workbookPath, relationships.find(relation => relation.getAttribute('Id') === sheetId));
  if (!sheetPath) {
    throw new Error('Missing XLSX schedule worksheet');
  }
  const worksheet = await readXmlPart(zip, sheetPath);
  const sheetData = worksheet.getElementsByTagNameNS(namespace, 'sheetData')[0];
  const sharedStringsPath = partTarget(workbookPath, relationships.find(
    relation => relation.getAttribute('Type') === `${RELATIONSHIP_NS}/sharedStrings`
  ));
  const sharedStrings = sharedStringsPath
    ? (await readXmlPart(zip, sharedStringsPath)).getElementsByTagNameNS(namespace, 'si')
    : [];

  let restoredNameWidth = 0;
  for (const row of sheetData.children) {
    const rowNumber = Number(row.getAttribute('r'));
    const cell = row.firstElementChild;
    if (rowNumber < 3 || rowNumber >= 3 + peopleCount || cell?.getAttribute('r') !== `A${rowNumber}`) {
      continue;
    }

    const type = cell.getAttribute('t');
    const value = cell.firstElementChild;
    if (!value || (type !== 'inlineStr' && type !== 's')) {
      continue;
    }
    const string = type === 's' ? sharedStrings[Number(value.textContent)] : value;
    const anonymizedId = spreadsheetText(string);
    const originalId = anonymizedId === undefined ? undefined : originalIdByAnonymizedId.get(anonymizedId);
    if (originalId === undefined) {
      continue;
    }

    const inlineString = worksheet.createElementNS(namespace, 'is');
    const text = worksheet.createElementNS(namespace, 't');
    if (originalId.trim() !== originalId) {
      text.setAttributeNS(XML_NS, 'xml:space', 'preserve');
    }
    text.textContent = escapeSpreadsheetText(originalId);
    inlineString.append(text);
    value.replaceWith(inlineString);
    cell.setAttribute('t', 'inlineStr');

    for (const line of originalId.split(/\r?\n/)) {
      // Estimate wide glyphs in units of the default font's digit width.
      let width = 2;
      for (const ch of line) {
        width += /[MWmw]|[^ -~]/.test(ch) ? 2 : 1;
      }
      restoredNameWidth = Math.max(restoredNameWidth, width);
    }
  }

  if (restoredNameWidth === 0) {
    return xlsxBlob;
  }

  const fitToPage = worksheet.getElementsByTagNameNS(namespace, 'pageSetUpPr')[0]?.getAttribute('fitToPage');
  if (fitToPage === '1' || fitToPage === 'true') {
    const names = Array.from(worksheet.getElementsByTagNameNS(namespace, 'col'))
      .find(column => column.getAttribute('min') === '1' && column.getAttribute('max') === '1');
    if (names) {
      const width = Math.max(Number(names.getAttribute('width') ?? 9), Math.min(restoredNameWidth, 255));
      names.setAttribute('width', String(width));
      names.setAttribute('customWidth', '1');
    }
  }

  zip.file(sheetPath, new XMLSerializer().serializeToString(worksheet), { createFolders: false });
  const output = await zip.generateAsync({ type: 'arraybuffer', compression: 'DEFLATE' });
  return new Blob([output], { type: XLSX_MIME_TYPE });
}
