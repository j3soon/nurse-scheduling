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

import { expect, test } from './test';
import { disableModalDialogs } from './helpers';

test('malformed YAML upload followed by valid upload restores downstream pages cleanly', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm a malformed upload does not corrupt the current preview.
   * 2. Upload a valid YAML file in the same session.
   * 3. Confirm the preview updates.
   * 4. Verify downstream pages reflect the valid uploaded state.
   */
  await disableModalDialogs(page);
  const validYaml = `apiVersion: test\ndescription: valid after invalid\ndates:\n  range:\n    startDate: 2026-05-01\n    endDate: 2026-05-01\n  groups: []\npeople:\n  items:\n    - id: P9\n      description: Uploaded person\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: Z\n      description: Zebra\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  const originalFirstLine = ((await page.locator('pre').textContent()) ?? '').split('\n')[0];
  await page.locator('input[type="file"]').setInputFiles({
    name: 'bad.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from('bad: [yaml', 'utf8'),
  });
  await expect(page.locator('pre')).toContainText(originalFirstLine);

  await page.locator('input[type="file"]').setInputFiles({
    name: 'good.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(validYaml, 'utf8'),
  });
  await expect(page.locator('pre')).toContainText('valid after invalid');
  await expect(page.locator('pre')).toContainText('P9');

  await page.goto('/people');
  await expect(page.getByText('1. P9', { exact: true })).toBeVisible();
  await page.goto('/shift-types');
  await expect(page.getByText('Z', { exact: true })).toBeVisible();
});
