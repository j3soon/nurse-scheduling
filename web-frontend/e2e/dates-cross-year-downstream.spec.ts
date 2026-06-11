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

test('cross-year date ranges use full YYYY-MM-DD IDs and still support downstream quick-add', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm shift requests initially has no configured dates.
   * 2. Apply a cross-year range from the Dates page.
   * 3. Confirm downstream date IDs use full YYYY-MM-DD format.
   * 4. Apply one quick-add request on the generated date and confirm the summary updates.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'cross year dates seed',
    dates: { range: {}, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  await expect(page.getByText('Please set up your dates first by visiting the')).toBeVisible();

  await page.goto('/dates');
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-12-31');
  await page.locator('#endDate').fill('2027-01-01');
  await page.getByRole('button', { name: /Apply|Update/ }).click();
  await expect(page.getByText('Duration: 2 days')).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 2026-12-31')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 2027-01-01')).toBeVisible();

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)').fill('2');
  const firstCell = page.locator('td[title="Click or drag to update preferences for P1 on date 2026-12-31"]');
  await firstCell.click();
  await expect(firstCell.getByText('D (+2)')).toBeVisible();
  await expect(page.getByText('Date: 2026-12-31')).toBeVisible();
});
