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

test('people drag reorder can be undone and redone through the shared item-group editor page', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed two people and confirm the initial order.
   * 2. Drag the second row above the first row on the People page.
   * 3. Undo to restore the original order.
   * 4. Redo to restore the reordered state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people reorder undo redo seed',
    dates: { range: {}, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const rows = peopleTable.locator('tbody tr');
  await expect(rows.nth(0)).toContainText('1. P1');
  await expect(rows.nth(1)).toContainText('2. P2');

  await rows.nth(1).dragTo(rows.nth(0));
  await expect(rows.nth(0)).toContainText('1. P2');
  await expect(rows.nth(1)).toContainText('2. P1');

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(rows.nth(0)).toContainText('1. P1');
  await expect(rows.nth(1)).toContainText('2. P2');

  await page.keyboard.press('Control+y');
  await expect(rows.nth(0)).toContainText('1. P2');
  await expect(rows.nth(1)).toContainText('2. P1');
});
