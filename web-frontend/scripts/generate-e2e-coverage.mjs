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

import fs from 'node:fs';
import path from 'node:path';
import MCR from 'monocart-coverage-reports';

const rawCoverageDir = path.join(process.cwd(), '.e2e-coverage', 'raw');
const outputDir = path.join(process.cwd(), 'coverage-e2e');

if (!fs.existsSync(rawCoverageDir)) {
  console.error(`No raw Playwright coverage found in ${rawCoverageDir}`);
  process.exit(1);
}

const coverageData = fs
  .readdirSync(rawCoverageDir)
  .filter((file) => file.endsWith('.json'))
  .flatMap((file) => JSON.parse(fs.readFileSync(path.join(rawCoverageDir, file), 'utf8')));

if (coverageData.length === 0) {
  console.error(`No coverage entries found in ${rawCoverageDir}`);
  process.exit(1);
}

const report = MCR({
  name: 'web-frontend-playwright',
  outputDir,
  reports: [
    ['console-summary'],
    ['html'],
    ['lcovonly', { file: 'lcov.info' }],
  ],
  entryFilter: (entry) => entry.url.startsWith('http://127.0.0.1:3000/_next/static/'),
  sourceFilter: (sourcePath) => sourcePath.includes(`${path.sep}src${path.sep}`),
});

try {
  await report.add(coverageData);
  await report.generate();
} catch (error) {
  console.error(error);
  process.exit(1);
}
