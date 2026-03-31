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

test('history edit modal updates the saved people-history summary', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the current people-history summary starts with the original shift type.
   * 2. Open the real history edit modal from the summary section and change the selection.
   * 3. Confirm the summary reflects the updated history after the modal closes.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'history modal seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: ['D'] }],
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
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentHistory.getByText(/H-1:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*N/)).toHaveCount(0);

  await currentHistory.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByText('Edit History - P1')).toBeVisible();
  await page.locator('select').selectOption('N');

  await expect(page.getByText('Edit History - P1')).toHaveCount(0);
  await expect(currentHistory.getByText(/H-1:\s*D/)).toHaveCount(0);
  await expect(currentHistory.getByText(/H-1:\s*N/)).toBeVisible();
});
