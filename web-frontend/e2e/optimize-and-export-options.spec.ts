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
import { disableModalDialogs, mockOptimizeAndExport, seedSchedulingState } from './helpers';

test('optimize and export sends the modified prettify and timeout options', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the optimize page starts with the default option values visible.
   * 2. Change prettify and timeout through the real form controls.
   * 3. Submit the optimize request and assert the backend payload reflects the changed values.
   */
  await disableModalDialogs(page);
  let submittedBody = '';
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize options seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  await expect(page.getByRole('heading', { name: 'Optimize and Export', exact: true })).toBeVisible();
  const prettifyCheckbox = page.getByLabel('Prettify XLSX');
  const timeoutInput = page.locator('input[type="number"]').first();
  await expect(prettifyCheckbox).toBeChecked();
  await expect(timeoutInput).toHaveValue('300');

  await prettifyCheckbox.uncheck();
  await timeoutInput.fill('45');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();

  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  expect(submittedBody).toContain('prettify');
  expect(submittedBody).toContain('false');
  expect(submittedBody).toContain('timeout');
  expect(submittedBody).toContain('45');
});
