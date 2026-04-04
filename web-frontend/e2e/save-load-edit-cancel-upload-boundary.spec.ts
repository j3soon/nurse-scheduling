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

test('canceling YAML edits keeps the draft isolated before a later upload', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original preview contains the original team name.
   * 2. Enter edit mode, make an unsaved rename, then cancel.
   * 3. Upload a different valid YAML file.
   * 4. Confirm the uploaded state appears and the canceled draft never leaks into the preview.
   */
  await disableModalDialogs(page);
  const uploadedYaml = `apiVersion: test\ndescription: upload boundary state\ndates:\n  range:\n    startDate: 2026-05-01\n    endDate: 2026-05-01\n  groups: []\npeople:\n  items:\n    - id: P9\n      description: Uploaded nurse\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: D\n      description: Day\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Group 1');

  await page.getByRole('button', { name: 'Edit YAML' }).click();
  const editor = page.locator('textarea');
  await editor.fill((await editor.inputValue()).replaceAll('Group 1', 'Draft Group'));
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(page.locator('pre')).toContainText('Group 1');
  await expect(page.locator('pre')).not.toContainText('Draft Group');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'uploaded.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(uploadedYaml, 'utf8'),
  });

  await expect(page.locator('pre')).not.toContainText('Group 1');
  await expect(page.locator('pre')).toContainText('upload boundary state');
  await expect(page.locator('pre')).toContainText('P9');
  await expect(page.locator('pre')).not.toContainText('Draft Group');
});
