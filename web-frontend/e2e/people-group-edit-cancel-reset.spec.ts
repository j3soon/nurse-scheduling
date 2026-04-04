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

test('canceling edit of an existing people group restores persisted values on reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded people group is visible.
   * 2. Open the edit form, change ID, description, and membership, then cancel.
   * 3. Confirm the rendered group still shows the original persisted values.
   * 4. Reopen edit mode and confirm the form inputs reset to the persisted values.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people group edit cancel seed',
    dates: { range: {}, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Original team' }],
      history: [],
    },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/people');
  const groupsTable = page.getByRole('heading', { name: 'People Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const row = groupsTable.locator('tr').filter({ has: page.getByText('Team Alpha', { exact: true }) }).first();
  await expect(row).toBeVisible();
  await expect(page.getByText('Original team')).toBeVisible();

  await row.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Team Omega');
  await page.getByPlaceholder('Enter group description (optional)').fill('Edited draft');
  await page.getByRole('checkbox', { name: 'P2', exact: true }).check();
  await page.getByRole('button', { name: 'Cancel' }).click();

  await expect(row).toBeVisible();
  await expect(page.getByText('Original team')).toBeVisible();
  await expect(page.getByText('Team Omega', { exact: true })).toHaveCount(0);

  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByPlaceholder('Enter group ID')).toHaveValue('Team Alpha');
  await expect(page.getByPlaceholder('Enter group description (optional)')).toHaveValue('Original team');
  await expect(page.getByRole('checkbox', { name: 'P1', exact: true })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'P2', exact: true })).not.toBeChecked();
});
