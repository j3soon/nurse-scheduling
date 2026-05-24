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

test('canceling date-range edits restores the original persisted values on reopen', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original persisted dates are visible.
   * 2. Enter unsaved replacement dates in edit mode and cancel.
   * 3. Confirm the original duration remains.
   * 4. Reopen edit mode and confirm the inputs reset to the persisted dates.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'dates cancel seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-03' }, groups: [] },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/dates');
  await expect(page.getByText('Duration: 3 days')).toBeVisible();

  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-06-01');
  await page.locator('#endDate').fill('2026-06-05');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('Duration: 3 days')).toBeVisible();
  await expect(page.getByText('Duration: 5 days')).toHaveCount(0);

  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await expect(page.locator('#startDate')).toHaveValue('2026-05-01');
  await expect(page.locator('#endDate')).toHaveValue('2026-05-03');
});
