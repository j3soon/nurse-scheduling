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
import { disableModalDialogs, disableOptimizeAnonymization, mockOptimizeAndExport, setDateRange } from './helpers';

test('a repeated optimize run after upstream edits submits updated yaml_content', async ({ page }) => {
  /*
   * Steps:
   * 1. Reset the schedule and run optimize once.
   * 2. Edit the People page state.
   * 3. Run optimize again.
   * 4. Confirm the second request body reflects the edit and differs from the first.
   */
  await disableModalDialogs(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();
  await setDateRange(page);

  const bodies: string[] = [];
  await mockOptimizeAndExport(page, { onSubmit: body => { bodies.push(body); } });

  await page.goto('/optimize-and-export');
  await disableOptimizeAnonymization(page);
  let downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await downloadPromise;
  expect(bodies[0]).toContain('Person 1');

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await peopleTable.locator('tr').filter({ has: page.getByText('1. Person 1', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Person X');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('1. Person X', { exact: true })).toBeVisible();

  await page.goto('/optimize-and-export');
  await disableOptimizeAnonymization(page);
  downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await downloadPromise;
  expect(bodies).toHaveLength(2);
  expect(bodies[1]).toContain('id: Person X');
  expect(bodies[1]).not.toContain('id: Person 1\n');
});
