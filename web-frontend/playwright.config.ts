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

import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

// Playwright reloads this config in test workers. Pass the chosen port to them
// so browser baseURL stays aligned with the server started by the runner.
const portEnvName = 'NURSE_SCHEDULING_PLAYWRIGHT_PORT';
const e2ePort = Number(process.env[portEnvName] ?? execFileSync(
  process.execPath,
  [path.join(__dirname, 'scripts/choose-e2e-port.mjs')],
  { encoding: 'utf8' },
));
process.env[portEnvName] = String(e2ePort);
const e2eBaseURL = `http://127.0.0.1:${e2ePort}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  workers: 8,
  use: {
    baseURL: e2eBaseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `bun run build:e2e && bunx serve@latest out -l ${e2ePort}`,
    env: {
      DISABLE_SENTRY: '1',
      E2E_COVERAGE: process.env.E2E_COVERAGE ?? '0',
      NEXT_PUBLIC_DISABLE_SENTRY: '1',
      NEXT_PUBLIC_DISABLE_HOSTED_OPTIMIZE_API: '1',
      NEXT_PUBLIC_AI_API_URL: '/ai',
    },
    url: e2eBaseURL,
    reuseExistingServer: false,
    timeout: 120000,
  },
});
