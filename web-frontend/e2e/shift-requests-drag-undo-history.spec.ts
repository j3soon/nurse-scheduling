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

test('revisiting a cell during one quick-add drag gesture should still produce a single undo step', async ({ page }) => {
  /*
   * Steps:
   * 1. Start from an empty request summary and enable quick-add mode.
   * 2. Simulate one drag gesture that visits date 01, date 02, then date 01 again.
   * 3. Release the mouse to commit the drag gesture and confirm both dates were updated.
   * 4. Trigger one undo and expect the whole gesture to disappear in one step.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'drag undo history seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-02' },
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

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  const currentRequests = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current Shift Requests' }) }).first();
  await expect(currentRequests.getByText('Date: 01')).toHaveCount(0);
  await expect(currentRequests.getByText('Date: 02')).toHaveCount(0);

  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)').fill('2');

  const firstCell = page.locator('td[title="Click or drag to update preferences for P1 on date 01"]');
  const secondCell = page.locator('td[title="Click or drag to update preferences for P1 on date 02"]');
  // Use locator-driven hover movement here. Raw page.mouse coordinate drags were
  // flaky in Playwright for this table even though the underlying quick-add path
  // works; locator hover keeps the browser event path stable for this regression test.
  await firstCell.hover();
  await page.mouse.down();
  await secondCell.hover();
  await firstCell.hover();
  await page.mouse.up();

  await expect(firstCell.getByText('D (+2)')).toBeVisible();
  await expect(secondCell.getByText('D (+2)')).toBeVisible();
  await expect(currentRequests.getByText('Date: 01, 02')).toBeVisible();

  await page.getByRole('heading', { name: 'Shift Requests', exact: true }).click();
  await page.keyboard.press('Control+z');

  await expect(currentRequests.getByText('Date: 01')).toHaveCount(0);
  await expect(currentRequests.getByText('Date: 02')).toHaveCount(0);
});
