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

test('canceling the people add form resets draft values when reopened', async ({ page }) => {
  /*
   * Steps:
   * 1. Reset to a fresh schedule and open the People page.
   * 2. Enter unsaved draft values in the add form and cancel.
   * 3. Confirm the draft item was not created.
   * 4. Reopen the add form and confirm the inputs are reset.
   */
  await disableModalDialogs(page);

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await page.getByRole('button', { name: 'Add Person' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Draft Person');
  await page.getByPlaceholder('Enter person description (optional)').fill('Unsaved draft');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('Draft Person', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Add Person' }).click();
  await expect(page.getByPlaceholder('Enter person ID')).toHaveValue('');
  await expect(page.getByPlaceholder('Enter person description (optional)')).toHaveValue('');
});
