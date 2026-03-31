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
import { disableModalDialogs } from './helpers';

test('new schedule resets the app to the default seeded state from the home page flow', async ({ page }) => {
  /*
   * Steps:
   * 1. Visit the home page and confirm the reset entry point is visible.
   * 2. Trigger the New Schedule confirmation flow from the real home page.
   * 3. Confirm the default seeded state appears on downstream management pages.
   */
  await disableModalDialogs(page);

  await page.goto('/');
  await expect(page.getByRole('button', { name: 'New Schedule' })).toBeVisible();

  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management' })).toBeVisible();
  await expect(page.getByText('1. Person 1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. Person 2', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Group 1', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  await expect(page.getByRole('heading', { name: 'Shift Type Management' })).toBeVisible();
  await expect(page.getByText('1. D', { exact: true })).toBeVisible();
  await expect(page.getByText('2. D+', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Day', { exact: true }).first()).toBeVisible();
});
