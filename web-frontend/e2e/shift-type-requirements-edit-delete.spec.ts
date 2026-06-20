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

test('shift type requirements can be edited and deleted through the page UI', async ({ page }) => {
  /*
   * Steps:
   * 1. Open shift type requirements with one seeded rule and confirm its original values.
   * 2. Edit the rule through the page UI and confirm the updated shift type and preferred count appear.
   * 3. Delete the same rule and confirm the list returns to the empty state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'requirement edit seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-02' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
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
      {
        type: 'shift type requirement',
        description: 'staffing rule',
        shiftType: ['D'],
        requiredNumPeople: 1,
        qualifiedPeople: ['P1'],
        preferredNumPeople: 2,
        date: ['01'],
        weight: -2,
      },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-type-requirements');
  await expect(page.getByRole('heading', { name: 'Shift Type Requirements', exact: true })).toBeVisible();
  await expect(page.getByText('staffing rule')).toBeVisible();
  await expect(page.getByText('Shift Types: D')).toBeVisible();
  await expect(page.getByText(/Required:\s*1/)).toBeVisible();
  await expect(page.getByText(/Preferred:\s*2/)).toBeVisible();

  await page.getByRole('button', { name: 'Edit' }).click();
  await page.getByRole('radio', { name: 'N', exact: true }).check();
  await page.locator('input[type="number"]').nth(1).fill('3');
  await page.getByRole('button', { name: 'Update', exact: true }).click();

  await expect(page.getByText('Shift Types: N')).toBeVisible();
  await expect(page.getByText(/Preferred:\s*3/)).toBeVisible();

  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('No requirements defined yet. Click "Add Requirement" to get started.')).toBeVisible();
});
