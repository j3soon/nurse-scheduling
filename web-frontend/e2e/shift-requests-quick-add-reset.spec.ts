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

test('quick-add preference inputs reset after canceling and reopening the mode', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm quick-add mode is initially closed.
   * 2. Open quick-add, select one shift type and set a non-default weight.
   * 3. Close quick-add mode without applying any cell changes.
   * 4. Reopen quick-add and confirm the checkbox and weight reset.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'quick add reset seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  await expect(page.getByRole('checkbox', { name: 'D', exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  const checkbox = page.getByRole('checkbox', { name: 'D', exact: true });
  const weightInput = page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)');
  await checkbox.check();
  await weightInput.fill('2');
  await expect(checkbox).toBeChecked();
  await expect(weightInput).toHaveValue('2');

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await expect(checkbox).toHaveCount(0);

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await expect(page.getByRole('checkbox', { name: 'D', exact: true })).not.toBeChecked();
  await expect(page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)')).toHaveValue('0');
});
