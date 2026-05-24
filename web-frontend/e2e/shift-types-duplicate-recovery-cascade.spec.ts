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

test('shift-type duplicate-ID recovery cascades the final corrected names downstream', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed shift-type and group references in downstream preference pages and confirm the originals.
   * 2. Attempt duplicate renames for both the shift type and the group, then recover with unique IDs.
   * 3. Confirm the corrected names persist on the Shift Types page.
   * 4. Revisit downstream pages and verify only the corrected IDs remain.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift-type duplicate recovery cascade seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
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
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 2, description: 'request rule' },
      { type: 'shift count', person: ['P1'], countDates: ['01'], countShiftTypes: ['Day Group'], expression: 'x >= T', target: 1, weight: 1, description: 'count rule' },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  await expect(page.getByText('Shift Type: D')).toBeVisible();
  await expect(page.getByText('Shift Type: DX')).toHaveCount(0);
  await page.goto('/shift-counts');
  await expect(page.getByText('Count Shift Types: Day Group')).toBeVisible();
  await expect(page.getByText('Count Shift Types: Daytime Group')).toHaveCount(0);

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

  const dayGroupRow = groupsTable.locator('tr').filter({ has: page.getByText('Day Group', { exact: true }) }).first();
  await dayGroupRow.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Night Group');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('This ID is already used by another shift type or group')).toBeVisible();
  await page.getByPlaceholder('Enter group ID').fill('Daytime Group');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(groupsTable.getByText('Daytime Group', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByText('Shift Type: DX')).toBeVisible();
  await expect(page.getByText('Shift Type: D', { exact: true })).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByText('Count Shift Types: Daytime Group')).toBeVisible();
  await expect(page.getByText('Count Shift Types: Day Group', { exact: true })).toHaveCount(0);
});
