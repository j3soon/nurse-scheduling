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

test('quick-add clear-mode drag clears existing requests across multiple cells', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm two seeded request cells are visible.
   * 2. Enter quick-add clear mode by leaving all shift types unselected.
   * 3. Drag across both cells.
   * 4. Confirm both cells and the grouped request summary are cleared.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'clear drag seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-02' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01', '02'], shiftType: ['D'], weight: 2 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  const currentRequests = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current Shift Requests' }) }).first();
  const firstCell = page.locator('td[title="Click to update preferences for P1 on date 01"]');
  const secondCell = page.locator('td[title="Click to update preferences for P1 on date 02"]');
  await expect(firstCell.getByText('D (+2)')).toBeVisible();
  await expect(secondCell.getByText('D (+2)')).toBeVisible();
  await expect(currentRequests.getByText('Date: 01, 02')).toBeVisible();

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  const dragFirstCell = page.locator('td[title="Click or drag to update preferences for P1 on date 01"]');
  const dragSecondCell = page.locator('td[title="Click or drag to update preferences for P1 on date 02"]');
  await dragFirstCell.hover();
  await page.mouse.down();
  await dragSecondCell.hover();
  await page.mouse.up();

  await expect(dragFirstCell.getByText('D (+2)')).toHaveCount(0);
  await expect(dragSecondCell.getByText('D (+2)')).toHaveCount(0);
  await expect(page.getByText('No shift requests defined yet. Click on any cell in the matrix above to add preferences.')).toBeVisible();
});
