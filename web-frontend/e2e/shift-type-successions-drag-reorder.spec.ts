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

test('shift type succession pattern reorder is preserved in the saved rule', async ({ page }) => {
  /*
   * Steps:
   * 1. Build a three-step succession pattern and confirm the original drag order.
   * 2. Drag the last pattern tag into the middle position.
   * 3. Save the rule and confirm the persisted pattern order matches the dragged order.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'succession drag seed',
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
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
        { id: 'A', description: 'Afternoon' },
      ],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-type-successions');
  await page.getByRole('button', { name: 'Add Succession' }).click();
  await page.getByPlaceholder('e.g., Forbid Evening -> Day succession').fill('Reordered pattern');
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('button', { name: 'D', exact: true }).click();
  await page.getByRole('button', { name: 'N', exact: true }).click();
  await page.getByRole('button', { name: 'A', exact: true }).click();

  const patternTags = page.locator('[draggable="true"]');
  await expect(patternTags).toHaveCount(3);
  await expect(patternTags.nth(0)).toContainText('D');
  await expect(patternTags.nth(1)).toContainText('N');
  await expect(patternTags.nth(2)).toContainText('A');

  await patternTags.nth(2).dragTo(patternTags.nth(1));
  await expect(patternTags.nth(0)).toContainText('D');
  await expect(patternTags.nth(1)).toContainText('A');
  await expect(patternTags.nth(2)).toContainText('N');

  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  const successionCard = page.locator('div').filter({ has: page.getByText('Reordered pattern') }).first();
  await expect(successionCard).toContainText(/D[\s\S]*A[\s\S]*N/);
});
