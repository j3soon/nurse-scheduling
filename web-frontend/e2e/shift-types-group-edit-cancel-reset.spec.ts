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

test('canceling edit of an existing shift-type group restores persisted values on reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded shift-type group is visible.
   * 2. Open the edit form, change ID, description, and membership, then cancel.
   * 3. Confirm the rendered group still shows the original persisted values.
   * 4. Reopen edit mode and confirm the form inputs reset to the persisted values.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift type group edit cancel seed',
    dates: { range: {}, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day shift' },
        { id: 'N', description: 'Night shift' },
      ],
      groups: [{ id: 'Day Group', members: ['D'], description: 'Original group' }],
    },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/shift-types');
  const groupsTable = page.getByRole('heading', { name: 'Shift Types Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const row = groupsTable.locator('tr').filter({ has: page.getByText('Day Group', { exact: true }) }).first();
  await expect(row).toBeVisible();
  await expect(page.getByText('Original group')).toBeVisible();

  await row.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Night Group');
  await page.getByPlaceholder('Enter group description (optional)').fill('Edited draft');
  await page.getByRole('checkbox', { name: 'N', exact: true }).check();
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(row).toBeVisible();
  await expect(page.getByText('Original group')).toBeVisible();
  await expect(page.getByText('Night Group', { exact: true })).toHaveCount(0);

  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByPlaceholder('Enter group ID')).toHaveValue('Day Group');
  await expect(page.getByPlaceholder('Enter group description (optional)')).toHaveValue('Original group');
  await expect(page.getByRole('checkbox', { name: 'D', exact: true })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'N', exact: true })).not.toBeChecked();
});
