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
import { disableModalDialogs, mockOptimizeAndExport, seedSchedulingState, setDateRange } from './helpers';

test('optimize and export surfaces backend validation errors for invalid upstream state', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a schedule that requires a manual date range and confirm the optimize page starts with no error.
   * 2. Mock the backend to return a validation-style error for that payload.
   * 3. Trigger optimize through the real form.
   * 4. Confirm the backend validation message is rendered to the user.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'invalid optimize state',
    dates: { range: {}, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });
  await setDateRange(page);

  await mockOptimizeAndExport(page, { status: 422, errorDetail: 'No people or dates configured' });

  await page.goto('/optimize-and-export');
  await expect(page.getByRole('heading', { name: 'Optimize and Export', exact: true })).toBeVisible();
  await expect(page.getByText('No people or dates configured')).toHaveCount(0);

  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('No people or dates configured')).toBeVisible();
});
