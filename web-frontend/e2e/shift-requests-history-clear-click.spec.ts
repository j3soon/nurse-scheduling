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

test('quick-add clear mode clears one history cell with a single click', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the seeded history summary and matrix start with one D entry.
   * 2. Enter quick-add clear mode by leaving all shift types unselected.
   * 3. Click the H-1 history cell once.
   * 4. Confirm the history summary returns to the empty state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'history clear click seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: ['D'] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentHistory.getByText(/H-1:\s*D/)).toBeVisible();

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await page.locator('td[title="Click or drag to set history position H-1 to clear"]').click();

  await expect(currentHistory.getByText(/H-1:\s*D/)).toHaveCount(0);
  await expect(page.getByText('No history entries defined yet. Click on any history cell in the matrix above to add entries.')).toBeVisible();
});
