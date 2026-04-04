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

test('save-load can ingest a moderately larger schedule and downstream pages stay responsive', async ({ page }) => {
  /*
   * Steps:
   * 1. Build a moderately larger YAML payload and confirm the current preview does not contain it.
   * 2. Upload the YAML through Save and Load.
   * 3. Confirm the preview updates.
   * 4. Verify key downstream pages render representative entries from the uploaded state.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  const peopleItems = Array.from({ length: 15 }, (_, index) => {
    const id = `P${String(index + 1).padStart(2, '0')}`;
    return `    - id: ${id}\n      description: Person ${index + 1}\n      history: []`;
  }).join('\n');
  const shiftTypeItems = Array.from({ length: 8 }, (_, index) => {
    return `    - id: S${index + 1}\n      description: Shift ${index + 1}`;
  }).join('\n');
  const largeYaml = `apiVersion: test\ndescription: large state smoke\ndates:\n  range:\n    startDate: 2026-07-01\n    endDate: 2026-07-10\n  groups: []\npeople:\n  items:\n${peopleItems}\n  groups: []\n  history: []\nshiftTypes:\n  items:\n${shiftTypeItems}\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).not.toContainText('large state smoke');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'large.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(largeYaml, 'utf8'),
  });

  await expect.poll(() => dialogs.length).toBe(2);
  await expect(page.locator('pre')).toContainText('large state smoke');
  await expect(page.locator('pre')).toContainText('P15');

  await page.goto('/people');
  await expect(page.getByText('1. P01', { exact: true })).toBeVisible();
  await expect(page.getByText('15. P15', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  await expect(page.getByText('S8', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P01 on date 01')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P15 on date 10')).toBeVisible();
});
