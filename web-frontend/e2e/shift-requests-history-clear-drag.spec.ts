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

test('quick-add clear-mode drag clears multiple history cells across one gesture', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the seeded history summary starts with two entries.
   * 2. Enter quick-add clear mode by leaving all shift types unselected.
   * 3. Drag across H-2 and H-1 using locator-driven hover movement.
   * 4. Confirm both history entries are cleared from the summary.
   *
   * Note:
   * Use locator hover plus page.mouse.down/up here, not raw page.mouse
   * coordinate drags. Raw coordinate drags were flaky in Playwright for this
   * table, while locator-driven hover reliably exercises the intended browser
   * event path.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'history clear drag seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: ['D', 'N'] }], groups: [], history: [] },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentHistory.getByText(/H-2:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*N/)).toBeVisible();

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  const firstHistoryCell = page.locator('td[title="Click or drag to set history position H-2 to clear"]');
  const secondHistoryCell = page.locator('td[title="Click or drag to set history position H-1 to clear"]');

  await firstHistoryCell.hover();
  await page.mouse.down();
  await secondHistoryCell.hover();
  await page.mouse.up();

  await expect(currentHistory.getByText(/H-2:\s*D/)).toHaveCount(0);
  await expect(currentHistory.getByText(/H-1:\s*N/)).toHaveCount(0);
  await expect(page.getByText('No history entries defined yet. Click on any history cell in the matrix above to add entries.')).toBeVisible();
});
