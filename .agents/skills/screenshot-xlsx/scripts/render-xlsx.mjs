#!/usr/bin/env node

import { existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, extname, resolve } from 'node:path';

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(2);
}

function usage() {
  console.log(`Usage:
  render-xlsx.mjs INPUT.xlsx OUTPUT.png [options]

Options:
  --module-root PATH    Directory whose node_modules contains exceljs and sharp
  --sheet NAME_OR_INDEX
  --range A1:M16
  --title TEXT
  --expect CELL=VALUE  Repeat to assert important cells before rendering
  --max-rows NUMBER    Default: 60
  --max-columns NUMBER Default: 30
  --force              Replace an existing output file
  --help`);
}

function parseArguments(argv) {
  const positional = [];
  const options = {
    moduleRoot: process.cwd(),
    sheet: undefined,
    range: undefined,
    title: undefined,
    expects: [],
    maxRows: 60,
    maxColumns: 30,
    force: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help') {
      usage();
      process.exit(0);
    }
    if (argument === '--force') {
      options.force = true;
      continue;
    }
    const valueOptions = new Map([
      ['--module-root', 'moduleRoot'],
      ['--sheet', 'sheet'],
      ['--range', 'range'],
      ['--title', 'title'],
      ['--max-rows', 'maxRows'],
      ['--max-columns', 'maxColumns'],
    ]);
    if (argument === '--expect') {
      const value = argv[index + 1];
      if (value === undefined) fail('--expect requires CELL=VALUE');
      options.expects.push(value);
      index += 1;
      continue;
    }
    if (valueOptions.has(argument)) {
      const value = argv[index + 1];
      if (value === undefined) fail(`${argument} requires a value`);
      options[valueOptions.get(argument)] = value;
      index += 1;
      continue;
    }
    if (argument.startsWith('--')) fail(`unknown option ${argument}`);
    positional.push(argument);
  }

  if (positional.length !== 2) {
    usage();
    fail('provide one input XLSX and one output PNG');
  }
  options.maxRows = Number.parseInt(String(options.maxRows), 10);
  options.maxColumns = Number.parseInt(String(options.maxColumns), 10);
  if (!Number.isInteger(options.maxRows) || options.maxRows < 1) fail('--max-rows must be a positive integer');
  if (!Number.isInteger(options.maxColumns) || options.maxColumns < 1) fail('--max-columns must be a positive integer');
  return { input: resolve(positional[0]), output: resolve(positional[1]), options };
}

function loadDependency(name, moduleRoot) {
  try {
    const requireFromRoot = createRequire(resolve(moduleRoot, 'package.json'));
    return requireFromRoot(requireFromRoot.resolve(name));
  } catch {
    fail(`cannot load ${name} from ${moduleRoot}; choose a --module-root containing that dependency`);
  }
}

function columnNumber(label) {
  return [...label.toUpperCase()].reduce((value, character) => value * 26 + character.charCodeAt(0) - 64, 0);
}

function columnLabel(number) {
  let label = '';
  let remaining = number;
  while (remaining > 0) {
    remaining -= 1;
    label = String.fromCharCode(65 + remaining % 26) + label;
    remaining = Math.floor(remaining / 26);
  }
  return label;
}

function parseRange(value) {
  const match = /^([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)$/.exec(value);
  if (!match) fail(`invalid range ${value}; expected A1:M16`);
  const range = {
    startColumn: columnNumber(match[1]),
    startRow: Number.parseInt(match[2], 10),
    endColumn: columnNumber(match[3]),
    endRow: Number.parseInt(match[4], 10),
  };
  if (range.startColumn > range.endColumn || range.startRow > range.endRow) fail(`range starts after it ends: ${value}`);
  return range;
}

function escapeXml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function argbToHex(argb, fallback) {
  return argb && /^[0-9a-fA-F]{8}$/.test(argb) ? `#${argb.slice(2)}` : fallback;
}

function borderWidth(style) {
  if (style === 'thick') return 3;
  if (style === 'medium' || style?.startsWith('medium')) return 2;
  return 1;
}

function displayText(cell) {
  return String(cell.text ?? '').replaceAll('\n', ' ').trim();
}

function textAnchor(cell) {
  const horizontal = cell.alignment?.horizontal;
  if (horizontal === 'center' || horizontal === 'centerContinuous') return 'middle';
  if (horizontal === 'right' || typeof cell.value === 'number') return 'end';
  return 'start';
}

function cellTextX(x, width, anchor) {
  if (anchor === 'middle') return x + width / 2;
  if (anchor === 'end') return x + width - 8;
  return x + 8;
}

function truncateText(value, maximumLength) {
  return value.length <= maximumLength ? value : `${value.slice(0, maximumLength - 3)}...`;
}

const { input, output, options } = parseArguments(process.argv.slice(2));
if (!existsSync(input)) fail(`input does not exist: ${input}`);
if (extname(input).toLowerCase() !== '.xlsx') fail('input must use the .xlsx extension');
if (extname(output).toLowerCase() !== '.png') fail('output must use the .png extension');
if (existsSync(output) && !options.force) fail(`output exists: ${output}; pass --force to replace it`);

const ExcelJsImport = loadDependency('exceljs', resolve(options.moduleRoot));
const ExcelJS = ExcelJsImport.default ?? ExcelJsImport;
const sharpImport = loadDependency('sharp', resolve(options.moduleRoot));
const sharp = sharpImport.default ?? sharpImport;
const workbook = new ExcelJS.Workbook();
await workbook.xlsx.readFile(input);
if (workbook.worksheets.length === 0) fail('workbook contains no worksheets');

let worksheet;
if (options.sheet === undefined) {
  worksheet = workbook.worksheets[0];
} else if (/^\d+$/.test(String(options.sheet))) {
  worksheet = workbook.getWorksheet(Number.parseInt(String(options.sheet), 10));
} else {
  worksheet = workbook.getWorksheet(String(options.sheet));
}
if (!worksheet) fail(`worksheet not found: ${options.sheet}`);

for (const expectation of options.expects) {
  const separator = expectation.indexOf('=');
  if (separator < 1) fail(`invalid expectation ${expectation}; expected CELL=VALUE`);
  const reference = expectation.slice(0, separator).toUpperCase();
  const expected = expectation.slice(separator + 1);
  if (!/^[A-Z]+\d+$/.test(reference)) fail(`invalid expectation cell: ${reference}`);
  const actual = displayText(worksheet.getCell(reference));
  if (actual !== expected) fail(`expected ${reference}=${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

const selectedRange = options.range
  ? parseRange(options.range)
  : {
      startColumn: 1,
      startRow: 1,
      endColumn: Math.max(worksheet.actualColumnCount, 1),
      endRow: Math.max(worksheet.actualRowCount, 1),
    };
const selectedRows = selectedRange.endRow - selectedRange.startRow + 1;
const selectedColumns = selectedRange.endColumn - selectedRange.startColumn + 1;
if (selectedRows > options.maxRows) fail(`range has ${selectedRows} rows; narrow it or raise --max-rows`);
if (selectedColumns > options.maxColumns) fail(`range has ${selectedColumns} columns; narrow it or raise --max-columns`);

const columns = [];
for (let number = selectedRange.startColumn; number <= selectedRange.endColumn; number += 1) {
  const column = worksheet.getColumn(number);
  if (column.hidden) continue;
  let longest = columnLabel(number).length;
  for (let row = selectedRange.startRow; row <= selectedRange.endRow; row += 1) {
    longest = Math.max(longest, displayText(worksheet.getCell(row, number)).length);
  }
  const workbookWidth = column.width ? Math.round(column.width * 7 + 12) : 0;
  const contentWidth = Math.round(longest * 7.2 + 24);
  columns.push({ number, width: Math.min(220, Math.max(58, workbookWidth, contentWidth)) });
}

const rows = [];
for (let number = selectedRange.startRow; number <= selectedRange.endRow; number += 1) {
  const row = worksheet.getRow(number);
  if (row.hidden) continue;
  const hasContent = columns.some(column => displayText(worksheet.getCell(number, column.number)) !== '');
  const workbookHeight = row.height ? Math.round(row.height * 96 / 72) : 0;
  rows.push({ number, height: Math.min(80, Math.max(hasContent ? 32 : 20, workbookHeight)) });
}
if (rows.length === 0 || columns.length === 0) fail('selected range contains no visible rows or columns');

const left = 50;
const top = 112;
const tableWidth = columns.reduce((sum, column) => sum + column.width, 0);
const tableHeight = rows.reduce((sum, row) => sum + row.height, 0);
const width = Math.max(720, left + tableWidth + 24);
const height = top + tableHeight + 52;
if (width > 6000 || height > 6000) fail(`rendered canvas ${width}x${height} is too large; narrow the range`);

const title = truncateText(options.title ?? basename(input), Math.max(20, Math.floor((width - 220) / 8)));
const fragments = [
  `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
  '<rect width="100%" height="100%" fill="#ffffff"/>',
  '<rect width="100%" height="46" fill="#217346"/>',
  `<text x="22" y="29" fill="#ffffff" font-family="Arial, sans-serif" font-size="17" font-weight="600">${escapeXml(title)}</text>`,
  `<text x="${width - 22}" y="29" text-anchor="end" fill="#e8f3ed" font-family="Arial, sans-serif" font-size="13">Rendered XLSX</text>`,
  '<rect y="46" width="100%" height="38" fill="#f5f7f6"/>',
  '<text x="22" y="70" xml:space="preserve" fill="#26332d" font-family="Arial, sans-serif" font-size="13">File   Home   Insert   Page Layout   Formulas   Data   Review   View</text>',
  `<rect x="0" y="84" width="${left}" height="28" fill="#f0f2f1" stroke="#d5dad7"/>`,
  '<defs>',
];

let y = top;
for (const row of rows) {
  let x = left;
  for (const column of columns) {
    fragments.push(`<clipPath id="cell-${row.number}-${column.number}"><rect x="${x + 3}" y="${y + 2}" width="${column.width - 6}" height="${row.height - 4}"/></clipPath>`);
    x += column.width;
  }
  y += row.height;
}
fragments.push('</defs>');

let x = left;
for (const column of columns) {
  fragments.push(`<rect x="${x}" y="84" width="${column.width}" height="28" fill="#f0f2f1" stroke="#d5dad7"/>`);
  fragments.push(`<text x="${x + column.width / 2}" y="103" text-anchor="middle" fill="#4b5563" font-family="Arial, sans-serif" font-size="12">${columnLabel(column.number)}</text>`);
  x += column.width;
}

y = top;
for (const row of rows) {
  fragments.push(`<rect x="0" y="${y}" width="${left}" height="${row.height}" fill="#f0f2f1" stroke="#d5dad7"/>`);
  fragments.push(`<text x="${left - 10}" y="${y + row.height / 2 + 4}" text-anchor="end" fill="#4b5563" font-family="Arial, sans-serif" font-size="12">${row.number}</text>`);
  x = left;
  for (const column of columns) {
    const cell = worksheet.getCell(row.number, column.number);
    const fill = cell.fill?.type === 'pattern' ? argbToHex(cell.fill.fgColor?.argb, '#ffffff') : '#ffffff';
    const rightBorderColor = argbToHex(cell.border?.right?.color?.argb, '#d9dedb');
    const bottomBorderColor = argbToHex(cell.border?.bottom?.color?.argb, '#d9dedb');
    fragments.push(`<rect x="${x}" y="${y}" width="${column.width}" height="${row.height}" fill="${fill}"/>`);
    fragments.push(`<line x1="${x + column.width}" y1="${y}" x2="${x + column.width}" y2="${y + row.height}" stroke="${rightBorderColor}" stroke-width="${borderWidth(cell.border?.right?.style)}"/>`);
    fragments.push(`<line x1="${x}" y1="${y + row.height}" x2="${x + column.width}" y2="${y + row.height}" stroke="${bottomBorderColor}" stroke-width="${borderWidth(cell.border?.bottom?.style)}"/>`);
    const text = displayText(cell);
    if (text) {
      const anchor = textAnchor(cell);
      const color = argbToHex(cell.font?.color?.argb, '#1f2937');
      const weight = cell.font?.bold ? '600' : '400';
      const style = cell.font?.italic ? 'italic' : 'normal';
      fragments.push(`<text x="${cellTextX(x, column.width, anchor)}" y="${y + row.height / 2 + 5}" text-anchor="${anchor}" clip-path="url(#cell-${row.number}-${column.number})" fill="${color}" font-family="Arial, sans-serif" font-size="13" font-weight="${weight}" font-style="${style}">${escapeXml(text)}</text>`);
    }
    x += column.width;
  }
  y += row.height;
}

fragments.push(`<rect x="0" y="${height - 40}" width="100%" height="40" fill="#f5f7f6" stroke="#d5dad7"/>`);
fragments.push(`<rect x="${left}" y="${height - 39}" width="110" height="38" fill="#ffffff"/>`);
fragments.push(`<rect x="${left}" y="${height - 3}" width="110" height="3" fill="#217346"/>`);
fragments.push(`<text x="${left + 55}" y="${height - 15}" text-anchor="middle" fill="#1f2937" font-family="Arial, sans-serif" font-size="13">${escapeXml(worksheet.name)}</text>`);
fragments.push('</svg>');

mkdirSync(dirname(output), { recursive: true });
await sharp(Buffer.from(fragments.join(''))).png().toFile(output);
console.log(JSON.stringify({
  input,
  output,
  sheet: worksheet.name,
  range: `${columnLabel(selectedRange.startColumn)}${selectedRange.startRow}:${columnLabel(selectedRange.endColumn)}${selectedRange.endRow}`,
  assertions: options.expects.length,
  width,
  height,
}));
