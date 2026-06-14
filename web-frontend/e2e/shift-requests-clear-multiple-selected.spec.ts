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

test('clear mode remains deterministic after multiple shift types were previously selected', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm a seeded request cell starts populated.
   * 2. Enter quick-add, select multiple shift types, then unselect them all.
   * 3. Click the populated cell in clear mode.
   * 4. Confirm the request is cleared.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'clear after multiselect seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }, { id: 'N', description: 'Night' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 2 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  const cell = page.locator('td[title="Click to update preferences for P1 on date 01"]');
  await expect(cell.getByText('D (+2)')).toBeVisible();

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  const checkboxD = page.getByRole('checkbox', { name: 'D', exact: true });
  const checkboxN = page.getByRole('checkbox', { name: 'N', exact: true });
  await checkboxD.check();
  await checkboxN.check();
  await checkboxD.uncheck();
  await checkboxN.uncheck();

  const dragCell = page.locator('td[title="Click or drag to update preferences for P1 on date 01"]');
  await dragCell.click();
  await expect(dragCell.getByText('D (+2)')).toHaveCount(0);
  await expect(page.getByText('No shift requests defined yet. Click on any cell in the matrix above to add preferences.')).toBeVisible();
});
