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
import { disableModalDialogs, setDateRange, mockOptimizationJobFlow, seedSchedulingState } from './helpers';

test('optimize request body stays on persisted state after an upstream edit is canceled', async ({ page }) => {
  /*
   * Steps:
   * 1. Reset to the default schedule and confirm the original person exists.
   * 2. Start an edit on the People page, change the ID, then cancel.
   * 3. Optimize with a mocked backend.
   * 4. Confirm yaml_content still contains the persisted original person and not the canceled draft.
  */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'alpha',
    description: 'canceled edit optimize seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'Person 1', description: '', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });
  await setDateRange(page);

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const personRow = peopleTable.locator('tr').filter({ has: page.getByText('1. Person 1', { exact: true }) });
  await personRow.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Person Draft');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(peopleTable.getByText('1. Person 1', { exact: true })).toBeVisible();
  await expect(peopleTable.getByText('1. Person Draft', { exact: true })).toHaveCount(0);

  let submittedBody = '';
  await mockOptimizationJobFlow(page, {
    onCreateJob: async request => {
      submittedBody = (await request.postData()) ?? '';
    },
  });

  await page.goto('/optimize-and-export');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await downloadPromise;

  expect(submittedBody).toContain('id: Person 1');
  expect(submittedBody).not.toContain('id: Person Draft');
});
