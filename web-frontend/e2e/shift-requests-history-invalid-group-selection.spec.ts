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

test('history quick-add ignores grouped shift-type selections and leaves history unchanged', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the current people-history summary starts empty.
   * 2. Enter quick-add and select a shift-type group rather than a concrete shift type.
   * 3. Click a history cell.
   * 4. Confirm no history entry is created.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'history invalid group seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }, { id: 'D+', description: 'Day Plus' }],
      groups: [{ id: 'Day', members: ['D', 'D+'], description: 'All day shift types' }],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  await expect(page.getByText('No history entries defined yet. Click on any history cell in the matrix above to add entries.')).toBeVisible();

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await page.getByRole('checkbox', { name: 'Day', exact: true }).check();
  await page.locator('td[title="Click or drag to set history position H-1 to Day"]').click();

  await expect(page.getByText('No history entries defined yet. Click on any history cell in the matrix above to add entries.')).toBeVisible();
  await expect(page.getByText(/H-1:/)).toHaveCount(0);
});
