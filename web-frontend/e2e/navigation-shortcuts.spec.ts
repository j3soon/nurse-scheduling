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

test('navigation keyboard shortcuts work globally but are suppressed while typing in inputs', async ({ page }) => {
  /*
   * Steps:
   * 1. Open people management, focus a real text input, and confirm arrow shortcuts do not navigate away.
   * 2. Blur the input and confirm arrow and number shortcuts navigate between pages.
   * 3. Confirm the active page changes exactly as the shortcuts imply.
   */
  await disableModalDialogs(page);

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add Person' }).click();
  const idInput = page.getByPlaceholder('Enter person ID');
  await idInput.click();
  await page.keyboard.press('ArrowRight');
  await expect(page).toHaveURL(/\/people$/);

  await idInput.blur();
  await page.keyboard.press('ArrowRight');
  await expect(page).toHaveURL(/\/shift-types$/);
  await expect(page.getByRole('heading', { name: 'Shift Type Management', exact: true })).toBeVisible();

  await page.keyboard.press('0');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('button', { name: 'New Schedule' })).toBeVisible();
});
