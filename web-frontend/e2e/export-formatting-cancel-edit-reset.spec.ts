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

test('canceling export layout style edits restores persisted rule values on reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded formatting rule is visible.
   * 2. Open edit mode, change colors, then cancel.
   * 3. Confirm the rendered rule still shows the original persisted values.
   * 4. Reopen edit mode and confirm the form inputs reset to the persisted values.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'formatting cancel edit seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/export-layout');
  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.locator('select').nth(1).selectOption('cell');
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByTitle('Enter background color in hex').fill('#00ff00');
  await page.getByTitle('Enter bottom border color in hex').fill('#0000ff');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Background: #00ff00')).toBeVisible();
  await expect(page.getByText('Bottom Border: #0000ff')).toBeVisible();

  await page.getByRole('button', { name: 'Edit' }).click();
  await page.getByTitle('Enter background color in hex').fill('#ff0000');
  await page.getByTitle('Enter bottom border color in hex').fill('#ffff00');
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(page.getByText('Background: #00ff00')).toBeVisible();
  await expect(page.getByText('Bottom Border: #0000ff')).toBeVisible();
  await expect(page.getByText('Background: #ff0000')).toHaveCount(0);

  await page.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByTitle('Enter background color in hex')).toHaveValue('#00ff00');
  await expect(page.getByTitle('Enter bottom border color in hex')).toHaveValue('#0000ff');
});
