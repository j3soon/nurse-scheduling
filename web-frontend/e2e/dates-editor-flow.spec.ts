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

test('setting a real date range through the Dates page propagates downstream', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm Shift Requests initially blocks progress because no dates are configured.
   * 2. Use the real Dates page editor to apply a three-day range and confirm the page shows the new duration.
   * 3. Revisit Shift Requests and confirm the generated date columns are now available.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'dates editor seed',
    dates: {
      range: {},
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
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  await expect(page.getByText('Please set up your dates first by visiting the')).toBeVisible();

  await page.goto('/dates');
  await expect(page.getByRole('heading', { name: 'Date Management', exact: true })).toBeVisible();
  await expect(page.getByText('Start Date:')).toBeVisible();
  await expect(page.getByText('End Date:')).toBeVisible();
  await expect(page.getByText('Duration:')).toHaveCount(0);

  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-05-01');
  await page.locator('#endDate').fill('2026-05-03');
  await page.getByRole('button', { name: 'Update' }).click();

  await expect(page.getByText('Duration: 3 days')).toBeVisible();
  const startDatePanel = page.getByText('Start Date:').locator('..');
  const endDatePanel = page.getByText('End Date:').locator('..');
  await expect(startDatePanel.getByText('Friday, May 1, 2026', { exact: true })).toBeVisible();
  await expect(endDatePanel.getByText('Sunday, May 3, 2026', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  await expect(page.getByText('Please set up your dates first by visiting the')).toHaveCount(0);
  await expect(page.getByTitle('Click to update preferences for P1 on date 01')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 02')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P1 on date 03')).toBeVisible();
});
