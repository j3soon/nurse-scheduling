import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, '../../..');
const moduleRoot = resolve(repositoryRoot, 'web-frontend');
const requireFromFrontend = createRequire(resolve(moduleRoot, 'package.json'));
const ExcelJsImport = requireFromFrontend('exceljs');
const ExcelJS = ExcelJsImport.default ?? ExcelJsImport;
const sharpImport = requireFromFrontend('sharp');
const sharp = sharpImport.default ?? sharpImport;
const renderer = resolve(scriptDirectory, 'render-xlsx.mjs');

function render(input, output, ...arguments_) {
  return spawnSync(
    process.execPath,
    [renderer, input, output, '--module-root', moduleRoot, ...arguments_],
    { encoding: 'utf8', timeout: 5_000 },
  );
}

function pixelAt(data, info, x, y) {
  const offset = (y * info.width + x) * info.channels;
  return [...data.subarray(offset, offset + 3)];
}

test('rejects invalid worksheet coordinates without hanging', async t => {
  const testDirectory = mkdtempSync(resolve(tmpdir(), 'render-xlsx-coordinates-'));
  t.after(() => rmSync(testDirectory, { recursive: true, force: true }));
  const input = resolve(testDirectory, 'fixture.xlsx');
  const output = resolve(testDirectory, 'output.png');
  const workbook = new ExcelJS.Workbook();
  workbook.addWorksheet('Sheet1').getCell('A1').value = 'value';
  await workbook.xlsx.writeFile(input);

  const excessiveColumn = 'Z'.repeat(1_000);
  const invalidArguments = [
    ['--range', 'A0:A1'],
    ['--range', 'XFE1:XFE1'],
    ['--range', 'A1048577:A1048577'],
    ['--range', `${excessiveColumn}1:${excessiveColumn}1`],
    ['--expect', 'XFE1=value'],
  ];

  for (const arguments_ of invalidArguments) {
    const result = render(input, output, ...arguments_);
    assert.equal(result.error, undefined, `renderer did not exit for ${arguments_.join(' ')}`);
    assert.equal(result.status, 2);
    assert.match(result.stderr, /worksheet coordinate is out of bounds/);
  }
});

test('renders distinct borders on all four sides', async t => {
  const testDirectory = mkdtempSync(resolve(tmpdir(), 'render-xlsx-borders-'));
  t.after(() => rmSync(testDirectory, { recursive: true, force: true }));
  const input = resolve(testDirectory, 'borders.xlsx');
  const output = resolve(testDirectory, 'borders.png');
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Borders');
  worksheet.getColumn(1).width = 15;
  worksheet.getRow(1).height = 30;
  worksheet.getCell('A1').value = 'Borders';
  worksheet.getCell('A1').border = {
    top: { style: 'thick', color: { argb: 'FFFF0000' } },
    left: { style: 'thick', color: { argb: 'FF00FF00' } },
    right: { style: 'thick', color: { argb: 'FF0000FF' } },
    bottom: { style: 'thick', color: { argb: 'FFFFFF00' } },
  };
  await workbook.xlsx.writeFile(input);

  const result = render(input, output, '--range', 'A1:A1');
  assert.equal(result.status, 0, result.stderr);

  const { data, info } = await sharp(output).raw().toBuffer({ resolveWithObject: true });
  assert.deepEqual(pixelAt(data, info, 100, 112), [255, 0, 0]);
  assert.deepEqual(pixelAt(data, info, 50, 130), [0, 255, 0]);
  assert.deepEqual(pixelAt(data, info, 167, 130), [0, 0, 255]);
  assert.deepEqual(pixelAt(data, info, 100, 152), [255, 255, 0]);
});
