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

test('dates page recovers from an invalid range and then applies a corrected range', async ({ page }) => {
  /*
   * Steps:
   * 1. Start with no dates configured and confirm the page shows no duration yet.
   * 2. Enter an invalid date range where the end date is before the start date.
   * 3. Confirm the validation error appears and no duration is applied.
   * 4. Correct the range and confirm downstream date columns appear.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'dates invalid recovery seed',
    dates: { range: {}, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/dates');
  await expect(page.getByRole('heading', { name: 'Date Management', exact: true })).toBeVisible();
  await expect(page.getByText('Duration:')).toHaveCount(0);

  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-05-03');
  await page.locator('#endDate').fill('2026-05-01');
  await page.getByRole('button', { name: /Apply|Update/ }).click();

  await expect(page.getByText('End date must be after start date')).toBeVisible();
  await expect(page.getByText('Duration:')).toHaveCount(0);

  await page.locator('#startDate').fill('2026-05-01');
  await page.locator('#endDate').fill('2026-05-03');
  await page.getByRole('button', { name: /Apply|Update/ }).click();

  await expect(page.getByText('Duration: 3 days')).toBeVisible();
  await expect(page.getByText('End date must be after start date')).toHaveCount(0);

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 01')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 02')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 03')).toBeVisible();
});
