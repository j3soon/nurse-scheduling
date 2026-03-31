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

test('shift type successions can be edited and deleted through the page UI', async ({ page }) => {
  /*
   * Steps:
   * 1. Open shift type successions with one seeded rule and confirm its original values.
   * 2. Edit the rule through the page UI and confirm the updated pattern appears.
   * 3. Delete the same rule and confirm the list returns to the empty state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'succession edit seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
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
        { id: 'E', description: 'Evening' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      {
        type: 'shift type successions',
        description: 'avoid morning after night',
        person: ['P1'],
        pattern: ['N', 'D'],
        date: ['01'],
        weight: -3,
      },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-type-successions');
  await expect(page.getByRole('heading', { name: 'Shift Type Successions', exact: true })).toBeVisible();
  await expect(page.getByText('avoid morning after night')).toBeVisible();
  await expect(page.getByText(/Pattern:/)).toBeVisible();
  await expect(page.getByTitle('Night')).toBeVisible();
  await expect(page.getByTitle('Day')).toBeVisible();

  await page.getByRole('button', { name: 'Edit' }).click();
  const editForm = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Edit Succession', exact: true }) }).first();
  await editForm.getByRole('button', { name: '×' }).nth(1).click();
  await page.getByRole('button', { name: 'E', exact: true }).click();
  await page.getByRole('button', { name: 'D', exact: true }).click();
  await page.getByRole('button', { name: 'Update', exact: true }).click();

  const successionCard = page.locator('div').filter({ has: page.getByText('avoid morning after night') }).first();
  await expect(successionCard.getByTitle('Night')).toBeVisible();
  await expect(successionCard.getByTitle('Evening')).toBeVisible();
  await expect(successionCard.getByTitle('Day')).toBeVisible();

  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('No successions defined yet. Click "Add Succession" to get started.')).toBeVisible();
});
