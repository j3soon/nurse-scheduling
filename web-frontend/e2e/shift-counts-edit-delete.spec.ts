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

test('shift counts can be edited and deleted through the page UI', async ({ page }) => {
  /*
   * Steps:
   * 1. Open shift counts with one seeded rule and confirm its original values.
   * 2. Edit the rule through the page UI and confirm the updated values appear.
   * 3. Delete the same rule and confirm the list returns to the empty state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift count edit seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }, { id: 'N', description: 'Night' }],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift count', person: ['P1'], countDates: ['01'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2, description: 'count rule' },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('count rule')).toBeVisible();
  await expect(page.getByText('Count Shift Types: D')).toBeVisible();

  await page.getByRole('button', { name: 'Edit' }).click();
  await page.getByRole('checkbox', { name: 'N', exact: true }).check();
  await page.getByRole('button', { name: 'Update', exact: true }).click();

  await expect(page.getByText('Count Shift Types: D, N')).toBeVisible();

  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('No shift counts defined yet. Click "Add Shift Count" to get started.')).toBeVisible();
});
