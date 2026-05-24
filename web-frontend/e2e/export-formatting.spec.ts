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

test('export formatting rules can be added, edited, and deleted through the page UI', async ({ page }) => {
  /*
   * Steps:
   * 1. Open export formatting and confirm there are no rules yet.
   * 2. Add a formatting rule and confirm it appears in the rules list.
   * 3. Edit the same rule and confirm the updated values replace the originals.
   * 4. Delete the rule and confirm the list is empty again.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'formatting seed',
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
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/export-layout');
  await expect(page.getByRole('heading', { name: 'Export Layout' })).toBeVisible();
  await expect(page.getByText('No style rules defined yet. Click "Add Export Rule" to get started.')).toBeVisible();

  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.locator('select').nth(1).selectOption('cell');
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByTitle('Enter background color in hex').fill('#00ff00');
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await expect(page.getByText('Shift Types: D')).toBeVisible();
  await expect(page.getByText('Background: #00ff00')).toBeVisible();

  await page.getByRole('button', { name: 'Edit' }).click();
  await page.getByTitle('Enter bottom border color in hex').fill('#ff0000');
  await page.getByRole('button', { name: 'Update', exact: true }).click();

  await expect(page.getByText('Background: #00ff00')).toBeVisible();
  await expect(page.getByText('Bottom Border: #ff0000')).toBeVisible();

  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('No style rules defined yet. Click "Add Export Rule" to get started.')).toBeVisible();
});
