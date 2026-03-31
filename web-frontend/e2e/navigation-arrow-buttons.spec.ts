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

test('navigation arrow buttons move between neighboring tabs with the expected boundaries', async ({ page }) => {
  /*
   * Steps:
   * 1. Warm the neighboring route once so the dev server has compiled it, then confirm the home page boundary state.
   * 2. Move forward with the next-arrow and verify the expected page loads.
   * 3. Move back with the previous-arrow and verify the home-page boundary state is restored.
   */
  await disableModalDialogs(page);

  await page.goto('/dates');
  await expect(page.getByRole('heading', { name: 'Date Management', exact: true })).toBeVisible();

  await page.goto('/');
  await expect(page.getByRole('button', { name: 'New Schedule' })).toBeVisible();
  await expect(page.getByTitle('Previous tab (←)')).toHaveCount(0);
  await expect(page.getByTitle('Next tab (→)')).toBeVisible();

  await page.getByTitle('Next tab (→)').click();
  await expect(page).toHaveURL(/\/dates$/);
  await expect(page.getByRole('heading', { name: 'Date Management', exact: true })).toBeVisible();
  await expect(page.getByTitle('Previous tab (←)')).toBeVisible();
  await expect(page.getByTitle('Next tab (→)')).toBeVisible();

  await page.getByTitle('Previous tab (←)').click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('button', { name: 'New Schedule' })).toBeVisible();
  await expect(page.getByTitle('Previous tab (←)')).toHaveCount(0);
});
