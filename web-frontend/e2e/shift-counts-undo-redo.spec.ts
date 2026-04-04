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

test('multiple shift-count additions can be undone and redone from the page', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the list starts empty.
   * 2. Add two different shift-count rules through the real page UI.
   * 3. Undo once to remove the second rule and confirm the first remains.
   * 4. Redo to restore the second rule.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift counts undo redo seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }, { id: 'N', description: 'Night' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-counts');
  await expect(page.getByText('No shift counts defined yet. Click "Add Shift Count" to get started.')).toBeVisible();

  await page.getByRole('button', { name: 'Add Shift Count' }).click();
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Count Shift Types: D')).toBeVisible();

  await page.getByRole('button', { name: 'Add Shift Count' }).click();
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'N', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Count Shift Types: N')).toBeVisible();

  await page.getByRole('heading', { name: 'Shift Counts', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('Count Shift Types: D')).toBeVisible();
  await expect(page.getByText('Count Shift Types: N')).toHaveCount(0);

  await page.keyboard.press('Control+y');
  await expect(page.getByText('Count Shift Types: N')).toBeVisible();
});
