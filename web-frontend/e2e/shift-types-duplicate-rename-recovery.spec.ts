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

test('shift-type and group rename flows recover from duplicate-ID validation and then save correctly', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed two shift types and two groups, then confirm the originals.
   * 2. Try renaming one shift type to a duplicate ID, confirm validation, then fix and save.
   * 3. Try renaming one group to a duplicate ID, confirm validation, then fix and save.
   * 4. Confirm the corrected IDs persist on the page.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift-type duplicate recovery seed',
    dates: { range: {}, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day shift' },
        { id: 'N', description: 'Night shift' },
      ],
      groups: [
        { id: 'Day Group', members: ['D'], description: 'Day group' },
        { id: 'Night Group', members: ['N'], description: 'Night group' },
      ],
    },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/shift-types');
  const itemsTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const groupsTable = page.getByRole('heading', { name: 'Shift Types Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');

  const dRow = itemsTable.locator('tr').filter({ has: page.getByText('1. D', { exact: true }) });
  await dRow.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter shift type ID').fill('N');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('This ID is already used by another shift type or group')).toBeVisible();
  await page.getByPlaceholder('Enter shift type ID').fill('DX');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(itemsTable.getByText('1. DX', { exact: true })).toBeVisible();
  await expect(itemsTable.getByText('1. D', { exact: true })).toHaveCount(0);

  const dayGroupRow = groupsTable.locator('tr').filter({ has: page.getByText('Day Group', { exact: true }) }).first();
  await dayGroupRow.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Night Group');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('This ID is already used by another shift type or group')).toBeVisible();
  await page.getByPlaceholder('Enter group ID').fill('Daytime Group');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(groupsTable.getByText('Daytime Group', { exact: true })).toBeVisible();
  await expect(groupsTable.getByText('Day Group', { exact: true })).toHaveCount(0);
});
