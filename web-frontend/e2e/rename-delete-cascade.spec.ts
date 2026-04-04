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

test('renaming then deleting a person removes the renamed reference from downstream pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original person appears on People and Shift Requests.
   * 2. Rename the person through the People page.
   * 3. Delete the renamed person.
   * 4. Verify downstream pages no longer show either the old or renamed reference.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'rename delete cascade seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 2 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(peopleTable.getByText('1. P1', { exact: true })).toBeVisible();
  await page.goto('/shift-requests');
  await expect(page.getByText('Person: P1')).toBeVisible();

  await page.goto('/people');
  const renamedRow = peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) });
  await renamedRow.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('P1X');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(peopleTable.getByText('1. P1X', { exact: true })).toBeVisible();

  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1X', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('P1X', { exact: true })).toHaveCount(0);

  await page.goto('/shift-requests');
  await expect(page.getByText('Person: P1X')).toHaveCount(0);
  await expect(page.getByText('Person: P1', { exact: true })).toHaveCount(0);
});
