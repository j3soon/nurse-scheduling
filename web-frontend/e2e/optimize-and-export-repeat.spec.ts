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

test('repeated optimize runs submit twice and keep a single success summary visible', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the optimize page starts without a success message.
   * 2. Run one mocked optimization and confirm the success summary appears.
   * 3. Run a second mocked optimization in the same session.
   * 4. Confirm both requests were sent while the page still shows a single success summary.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize repeat seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  let callCount = 0;
  await mockOptimizeAndExport(page, { onSubmit: () => { callCount += 1; } });

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);

  const firstDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await firstDownloadPromise;
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  await expect(page.getByText('output.xlsx')).toBeVisible();

  const secondDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await secondDownloadPromise;
  await expect.poll(() => callCount).toBe(2);
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(1);
  await expect(page.getByText('output.xlsx')).toHaveCount(1);
});
