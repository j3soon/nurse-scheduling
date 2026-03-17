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

import { expect, test } from '@playwright/test';
import { disableModalDialogs, seedSchedulingState } from './helpers';

test('shrinking the date range removes stale date references from downstream pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm downstream pages currently reference the second date before any edit.
   * 2. Shrink the managed date range from two days down to one day.
   * 3. Revisit downstream pages and confirm references to the removed date are gone.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'date shrink seed',
    dates: {
      range: {
        startDate: '2026-05-01',
        endDate: '2026-05-02',
      },
      groups: [],
    },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
      ],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['02'], shiftType: ['D'], weight: 2, description: 'second-day request' },
      { type: 'shift count', person: ['P1'], countDates: ['01', '02'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2, description: 'date window count' },
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('date window count')).toBeVisible();
  await expect(page.getByText('Count Dates: 01, 02')).toBeVisible();
  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 02')).toBeVisible();

  await page.goto('/dates');
  await expect(page.getByRole('heading', { name: 'Date Management' })).toBeVisible();
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#endDate').fill('2026-05-01');
  await page.getByRole('button', { name: 'Update' }).click();

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  await expect(page.getByText('second-day request')).toHaveCount(0);
  await expect(page.getByText('Date: 02')).toHaveCount(0);
  await expect(page.getByTitle('Click to update preferences for P1 on date 02')).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('date window count')).toBeVisible();
  await expect(page.getByText('Count Dates: 01')).toBeVisible();
  await expect(page.getByText('Count Dates: 01, 02')).toHaveCount(0);
});
