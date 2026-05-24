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

test('shift preference editor persists mixed manual and infinity values through reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Open the shift requests page and confirm there is no saved preference summary yet.
   * 2. Open the matrix editor, change two rows with different input styles, and save.
   * 3. Confirm the summary updates on the page.
   * 4. Reopen the matrix and confirm the persisted values are restored.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift request modal seed',
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
        { id: 'N', description: 'Night' },
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
  await expect(page.getByText('D (+∞)')).toHaveCount(0);
  await expect(page.getByText('N (-3)')).toHaveCount(0);

  await page.getByTitle('Click to update preferences for P1 on date 01').click();
  await expect(page.locator('h2').filter({ hasText: 'Shift Preference Matrix' })).toBeVisible();

  const dayRow = page.locator('tr').filter({ has: page.getByText(/^D$/) }).first();
  await dayRow.getByRole('button', { name: '+∞' }).click();

  const nightRow = page.locator('tr').filter({ has: page.getByText(/^N$/) }).first();
  await nightRow.getByRole('textbox').fill('-3');

  await page.getByRole('button', { name: 'Save Preferences' }).click();

  await expect(page.getByText('D (+∞)')).toBeVisible();
  await expect(page.getByText('N (-3)')).toBeVisible();

  await page.getByTitle('Click to update preferences for P1 on date 01').click();
  await expect(page.locator('h2').filter({ hasText: 'Shift Preference Matrix' })).toBeVisible();
  await expect(dayRow.getByRole('textbox')).toHaveValue('Infinity');
  await expect(nightRow.getByRole('textbox')).toHaveValue('-3');
  await expect(page.getByText('Active Preferences Summary')).toBeVisible();
  await expect(page.getByText('D').first()).toBeVisible();
  await expect(page.getByText('N').first()).toBeVisible();
});
