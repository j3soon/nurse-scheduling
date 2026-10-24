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

import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

// Captures the user guide screenshots from a production build. Run `bun run docs:screenshots`.
// Show the latest release version, as readers of the deployed guide see it.
// Playwright reloads this config in workers, so keep the version in the environment.
const repo = path.join(__dirname, '..');
process.env.APP_VERSION_OVERRIDE ||= execFileSync(
  'git',
  ['-c', `safe.directory=${repo}`, '-C', repo, 'describe', '--tags', '--abbrev=0'],
  { encoding: 'utf8' },
).trim();

export default defineConfig({
  testDir: './docs-screenshots',
  globalSetup: './docs-screenshots/build.ts',
  fullyParallel: true,
  reporter: 'list',
  workers: 4,
  use: {
    ...devices['Desktop Chrome'],
    // The capture answers this origin from the exported build in `out/`.
    baseURL: 'https://nursescheduling.org',
    locale: 'en-US',
    timezoneId: 'UTC',
  },
});
