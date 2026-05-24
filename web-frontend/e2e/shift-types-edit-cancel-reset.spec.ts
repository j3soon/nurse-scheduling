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
import { disableModalDialogs, seedSchedulingState } from './helpers';

test('canceling edit of an existing shift type restores persisted values on reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded shift type is visible.
   * 2. Open the edit form, change the ID and description, then cancel.
   * 3. Confirm the rendered row still shows the original persisted values.
   * 4. Reopen edit mode and confirm the form inputs reset to the persisted values.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift type edit cancel seed',
    dates: { range: {}, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day shift' }], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/shift-types');
  const table = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const row = table.locator('tr').filter({ has: page.getByText('1. D', { exact: true }) });
  await expect(row).toBeVisible();
  await expect(page.getByText('Day shift')).toBeVisible();

  await row.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter shift type ID').fill('DX');
  await page.getByPlaceholder('Enter shift type description (optional)').fill('Edited draft');
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(page.getByText('1. D', { exact: true })).toBeVisible();
  await expect(page.getByText('Day shift')).toBeVisible();
  await expect(page.getByText('1. DX', { exact: true })).toHaveCount(0);

  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByPlaceholder('Enter shift type ID')).toHaveValue('D');
  await expect(page.getByPlaceholder('Enter shift type description (optional)')).toHaveValue('Day shift');
});
