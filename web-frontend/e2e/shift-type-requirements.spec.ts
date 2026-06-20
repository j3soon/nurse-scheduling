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

test('adds a shift type requirement through the real form flow', async ({ page }) => {
  /*
   * Steps:
   * 1. Open shift type requirements and confirm the target rule is not present yet.
   * 2. Add a new requirement through the real form controls.
   * 3. Confirm the saved card shows the expected description and selections.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'requirement seed',
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

  await page.goto('/shift-type-requirements');
  await expect(page.getByRole('heading', { name: 'Shift Type Requirements' })).toBeVisible();
  await expect(page.getByText('Need one day nurse')).toHaveCount(0);
  await expect(page.getByText('Shift Types: D')).toHaveCount(0);
  await page.getByRole('button', { name: 'Add Requirement' }).click();

  await page.getByPlaceholder('e.g., Night shifts need senior nurses').fill('Need one day nurse');
  await page.getByRole('radio', { name: 'D', exact: true }).check();
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await expect(page.getByText('Need one day nurse')).toBeVisible();
  await expect(page.getByText('Shift Types: D')).toBeVisible();
  await expect(page.getByText('Qualified: P1')).toBeVisible();
  await expect(page.getByText('Dates: 01')).toBeVisible();
});
