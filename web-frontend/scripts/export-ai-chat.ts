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

// This code is mostly AI generated.

import { readFileSync, writeFileSync, renameSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { buildSavedChatExport } from '../src/app/experimental-ai/savedChatExport';

const args = process.argv.slice(2);
if (args.length === 0 || args.includes('--help')) {
  console.log('Usage: bun scripts/export-ai-chat.ts OUTPUT.html|OUTPUT.md [--snapshot SNAPSHOT.json]');
  process.exit(args.includes('--help') ? 0 : 2);
}
const output = resolve(args[0]);
const format = output.endsWith('.html') ? 'html' : output.endsWith('.md') ? 'markdown' : null;
if (format === null || (args.length !== 1 && !(args.length === 3 && args[1] === '--snapshot'))) {
  console.error('Choose an .html or .md output path.');
  process.exit(2);
}
const temporary = `${output}.${process.pid}.tmp`;
try {
  const input = readFileSync(args.length === 3 ? args[2] : 0, 'utf8');
  const document = buildSavedChatExport(JSON.parse(input), format);
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(temporary, document, 'utf8');
  renameSync(temporary, output);
  console.log(`Exported ${output}`);
} catch {
  rmSync(temporary, { force: true });
  console.error('Could not export the saved chat snapshot. The output file was not changed.');
  process.exit(1);
}
