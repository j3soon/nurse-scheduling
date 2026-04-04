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

test('shrinking a month-spanning range back into one month reverts downstream IDs to DD format', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm a seeded month-spanning range renders MM-DD IDs downstream.
   * 2. Update the range so it stays within one month.
   * 3. Confirm the Dates page shows the shorter duration.
   * 4. Revisit Shift Requests and confirm the IDs now use DD format.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'range shrink format seed',
    dates: { range: { startDate: '2026-05-31', endDate: '2026-06-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 05-31')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 06-01')).toBeVisible();

  await page.goto('/dates');
  await page.getByRole('button', { name: /Set Date Range|Edit Date Range/ }).click();
  await page.locator('#startDate').fill('2026-05-31');
  await page.locator('#endDate').fill('2026-05-31');
  await page.getByRole('button', { name: /Apply|Update/ }).click();
  await expect(page.getByText('Duration: 1 days')).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 31')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 05-31')).toHaveCount(0);
});
