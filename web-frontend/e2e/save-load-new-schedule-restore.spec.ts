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

test('new schedule reset can be followed by restoring the just-created state from YAML', async ({ page }) => {
  /*
   * Steps:
   * 1. Create real UI state by adding a person and confirm it appears on the People page.
   * 2. Capture the YAML for that created state from Save and Load.
   * 3. Reset the app through the New Schedule flow and confirm the created person disappears.
   * 4. Upload the captured YAML and confirm the created person returns.
   */
  await disableModalDialogs(page);
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await page.getByRole('button', { name: 'Add Person' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Restore Person');
  await page.getByPlaceholder('Enter person description (optional)').fill('Created through UI');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Restore Person', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Restore Person');
  const yamlText = await page.locator('pre').textContent();
  expect(yamlText).toContain('Restore Person');

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByText('Restore Person', { exact: true })).toHaveCount(0);

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'restore-created.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await expect.poll(() => dialogs.some(message => message.includes('YAML file loaded successfully!'))).toBe(true);

  await page.goto('/people');
  await expect(page.getByText('Restore Person', { exact: true })).toBeVisible();
});
