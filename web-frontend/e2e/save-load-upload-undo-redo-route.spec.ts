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

test('uploaded state can be undone and redone across route changes', async ({ page }) => {
  /*
   * Steps:
   * 1. Reset to a clean schedule and confirm the uploaded entities are not present.
   * 2. Upload valid YAML through Save and Load and confirm downstream pages reflect it.
   * 3. Navigate to another page and undo the upload through the global shortcut.
   * 4. Navigate again and redo the upload to confirm history survives route changes.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  const uploadYaml = `apiVersion: test\ndescription: upload undo redo state\ndates:\n  range:\n    startDate: 2026-05-01\n    endDate: 2026-05-01\n  groups: []\npeople:\n  items:\n    - id: P9\n      description: Uploaded nurse\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: ZX\n      description: Uploaded shift\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByText('P9', { exact: true })).toHaveCount(0);
  await page.goto('/shift-types');
  await expect(page.getByText('ZX', { exact: true })).toHaveCount(0);

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'upload.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(uploadYaml, 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(2);

  await page.goto('/people');
  await expect(page.getByText('1. P9', { exact: true })).toBeVisible();
  await page.goto('/shift-types');
  await expect(page.getByText('ZX', { exact: true })).toBeVisible();

  await page.getByRole('heading', { name: 'Shift Type Management', exact: true }).click();
  await page.keyboard.press('Control+z');

  await page.goto('/people');
  await expect(page.getByText('P9', { exact: true })).toHaveCount(0);
  await page.goto('/shift-types');
  await expect(page.getByText('ZX', { exact: true })).toHaveCount(0);

  await page.getByRole('heading', { name: 'Shift Type Management', exact: true }).click();
  await page.keyboard.press('Control+y');

  await page.goto('/people');
  await expect(page.getByText('1. P9', { exact: true })).toBeVisible();
  await page.goto('/shift-types');
  await expect(page.getByText('ZX', { exact: true })).toBeVisible();
});
