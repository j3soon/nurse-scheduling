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

test('canceling edit of an existing person restores persisted values on reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded person is visible.
   * 2. Open the edit form, change the ID and description, then cancel.
   * 3. Confirm the rendered row still shows the original persisted values.
   * 4. Reopen edit mode and confirm the form inputs reset to the persisted values.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people edit cancel seed',
    dates: { range: {}, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const row = peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) });
  await expect(row).toBeVisible();
  await expect(page.getByText('Primary nurse')).toBeVisible();

  await row.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('P1X');
  await page.getByPlaceholder('Enter person description (optional)').fill('Edited draft');
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('Primary nurse')).toBeVisible();
  await expect(page.getByText('P1X', { exact: true })).toHaveCount(0);

  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByPlaceholder('Enter person ID')).toHaveValue('P1');
  await expect(page.getByPlaceholder('Enter person description (optional)')).toHaveValue('Primary nurse');
});
