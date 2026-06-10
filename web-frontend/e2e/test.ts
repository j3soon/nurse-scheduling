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

import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test as base } from '@playwright/test';

const rawCoverageDir = path.join(process.cwd(), '.e2e-coverage', 'raw');

const isCoverageEnabled = process.env.E2E_COVERAGE === '1';

const test = base.extend({
  page: async ({ page }, runPage, testInfo) => {
    // Tag each Playwright worker so the app can keep worker-local storage state
    // isolated while still using the normal storage key for real users.
    await page.addInitScript((workerNamespace) => {
      window.__PLAYWRIGHT_WORKER_NAMESPACE__ = workerNamespace;
    }, `worker-${testInfo.workerIndex}`);

    await page.route(/^https?:\/\/api\.nursescheduling\.org\/.*/, async route => {
      await route.abort('blockedbyclient');
    });

    if (isCoverageEnabled) {
      await page.coverage.startJSCoverage({
        resetOnNavigation: false,
      });
    }

    await runPage(page);

    if (!isCoverageEnabled) {
      return;
    }

    const coverage = await page.coverage.stopJSCoverage();
    const safeTitle = testInfo.titlePath.join('__').replace(/[^a-zA-Z0-9_-]+/g, '_');
    const outputPath = path.join(rawCoverageDir, `${safeTitle}-${testInfo.retry}.json`);

    await fs.mkdir(rawCoverageDir, { recursive: true });
    await fs.writeFile(outputPath, JSON.stringify(coverage), 'utf8');
  },
});

export { expect, test };
