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
import { disableModalDialogs, disableOptimizeAnonymization, mockOptimizeAndExport, setDateRange, waitForStoredCurrentSchedulingData } from './helpers';

test('optimize request body follows undo and redo of upstream edits', async ({ page }) => {
  /*
   * Steps:
   * 1. Reset to the default schedule and add a new person upstream.
   * 2. Undo that edit and optimize once, confirming the request body excludes the new person.
   * 3. Redo the edit and optimize again, confirming the request body includes the new person.
   */
  await disableModalDialogs(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();
  await setDateRange(page);

  await page.goto('/people');
  await page.getByRole('button', { name: 'Add Person' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Undo Redo Nurse');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Undo Redo Nurse', { exact: true })).toBeVisible();

  const submittedBodies: string[] = [];
  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBodies.push(body); } });

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('Undo Redo Nurse', { exact: true })).toHaveCount(0);

  await page.goto('/optimize-and-export');
  await disableOptimizeAnonymization(page);
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect.poll(() => submittedBodies.length).toBe(1);
  expect(submittedBodies[0]).not.toContain('Undo Redo Nurse');

  await page.goto('/people');
  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+y');
  await waitForStoredCurrentSchedulingData(page, 'Undo Redo Nurse');
  await expect(page.getByText('Undo Redo Nurse', { exact: true })).toBeVisible();

  await page.goto('/optimize-and-export');
  await disableOptimizeAnonymization(page);
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect.poll(() => submittedBodies.length).toBe(2);
  expect(submittedBodies[1]).toContain('Undo Redo Nurse');
});
