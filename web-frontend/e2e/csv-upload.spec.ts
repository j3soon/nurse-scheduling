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

test('csv uploads recover from invalid history input and populate downstream request/history state', async ({ page }) => {
  /*
   * Steps:
   * 1. Open shift requests in quick-add mode and confirm no imported request/history summary is visible yet.
   * 2. Upload an invalid people-history CSV and confirm the page remains in the original empty state.
   * 3. Upload valid people-history and shift-requests CSV files.
   * 4. Confirm the imported request and history summary appear.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'csv upload seed',
    dates: {
      range: {
        startDate: '2026-05-01',
        endDate: '2026-05-01',
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
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  const currentRequests = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current Shift Requests' }) }).first();
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentRequests.getByText('Person: P1', { exact: true })).toHaveCount(0);
  await expect(currentRequests.getByText(/Shift Type:\s*D/)).toHaveCount(0);
  await expect(currentHistory.getByText(/H-2:\s*D/)).toHaveCount(0);
  await expect(currentHistory.getByText(/H-1:\s*D/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  const weightInput = page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)');
  await expect(weightInput).toBeVisible();
  await weightInput.fill('2');

  const uploadInputs = page.locator('input[type="file"]');
  await uploadInputs.nth(0).setInputFiles({
    name: 'people-history-invalid.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('P1,D\n', 'utf8'),
  });
  await expect(page.getByText('No history entries defined yet. Click on any history cell in the matrix above to add entries.')).toBeVisible();
  await expect(currentRequests.getByText('Person: P1', { exact: true })).toHaveCount(0);
  await expect(currentRequests.getByText(/Shift Type:\s*D/)).toHaveCount(0);

  await uploadInputs.nth(0).setInputFiles({
    name: 'people-history.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('P1,D,2\n', 'utf8'),
  });
  await uploadInputs.nth(1).setInputFiles({
    name: 'shift-requests.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('P1,D\n', 'utf8'),
  });

  await expect(currentRequests.getByText('Person: P1', { exact: true })).toBeVisible();
  await expect(currentRequests.getByText(/Shift Type:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-2:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*D/)).toBeVisible();
});
