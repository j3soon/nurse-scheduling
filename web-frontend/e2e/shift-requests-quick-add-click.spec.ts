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

test('single quick-add click applies one shift request cell', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the request summary is empty before quick-add mode starts.
   * 2. Enable quick-add, choose one shift type and weight.
   * 3. Click one request cell.
   * 4. Confirm that one cell and one grouped request were created.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'single quick-add click seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-02' },
      groups: [],
    },
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

  await page.goto('/shift-requests');
  const currentRequests = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current Shift Requests' }) }).first();
  await expect(currentRequests.getByText('Date: 01')).toHaveCount(0);

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)').fill('2');

  const firstCell = page.locator('td[title="Click or drag to update preferences for P1 on date 01"]');
  await firstCell.click();

  await expect(firstCell.getByText('D (+2)')).toBeVisible();
  await expect(currentRequests.getByText('Date: 01')).toBeVisible();
  await expect(currentRequests.getByText(/Shift Type:\s*D/)).toHaveCount(1);
});
