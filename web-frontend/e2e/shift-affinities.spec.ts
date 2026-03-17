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

test('adds a shift affinity through the real form flow', async ({ page }) => {
  /*
   * Steps:
   * 1. Open shift affinities and confirm the target affinity card does not exist yet.
   * 2. Add a new affinity through the real form controls.
   * 3. Confirm the saved affinity shows the selected date, people, and shift type.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift affinity seed',
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

  await page.goto('/shift-affinities');
  await expect(page.getByRole('heading', { name: 'Shift Affinities', exact: true })).toBeVisible();
  await expect(page.getByText('Dates: 01')).toHaveCount(0);
  await expect(page.getByText('People 1: P1')).toHaveCount(0);
  await expect(page.getByText('People 2: P1')).toHaveCount(0);
  await expect(page.getByText('Shift Types: D')).toHaveCount(0);
  await page.getByRole('button', { name: 'Add Shift Affinity' }).click();

  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'P1', exact: true }).nth(0).check();
  await page.getByRole('checkbox', { name: 'P1', exact: true }).nth(1).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await expect(page.getByText('Dates: 01')).toBeVisible();
  await expect(page.getByText('People 1: P1')).toBeVisible();
  await expect(page.getByText('People 2: P1')).toBeVisible();
  await expect(page.getByText('Shift Types: D')).toBeVisible();
});
