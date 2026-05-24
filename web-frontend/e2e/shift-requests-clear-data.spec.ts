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

test('clear-data actions remove current requests and history summaries', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed the page with one current request and one history summary and confirm both are visible.
   * 2. Clear all requests and confirm the current requests section empties.
   * 3. Clear all people history and confirm the history section empties.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'clear data seed',
    dates: {
      range: {
        startDate: '2026-05-01',
        endDate: '2026-05-01',
      },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: ['D', 'D'] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 2, description: 'keep me' },
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();

  const currentRequests = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current Shift Requests' }) }).first();
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentRequests.getByText('Person: P1', { exact: true })).toBeVisible();
  await expect(currentRequests.getByText(/Shift Type:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-2:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*D/)).toBeVisible();

  await page.getByRole('button', { name: 'Clear All Requests' }).click();
  await expect(page.getByText('No shift requests defined yet. Click on any cell in the matrix above to add preferences.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Current Shift Requests' })).toBeVisible();

  await page.getByRole('button', { name: 'Clear All People History' }).click();
  await expect(page.getByText('No history entries defined yet. Click on any history cell in the matrix above to add entries.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Current People History' })).toBeVisible();
});
