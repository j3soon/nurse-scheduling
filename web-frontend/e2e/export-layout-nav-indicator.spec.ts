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

test('shows the custom export layout indicator on the navigation tab only when a layout is stored', async ({ page }) => {
  /*
   * Steps:
   * 1. Load the home page with the default state and confirm the indicator is absent.
   * 2. Seed a stored export layout, navigate to another page, and confirm the indicator appears on the Export Layout tab.
   * 3. Confirm the indicator stays visible on a different page.
   */
  await disableModalDialogs(page);

  await page.goto('/');
  await expect(page.getByTestId('custom-export-layout-indicator')).toHaveCount(0);

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'custom export layout navigation seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-08' },
      groups: [],
    },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [
        { type: 'cell', people: ['P1'], dates: ['01'], shiftTypes: ['D'], backgroundColor: '#111111' },
      ],
    },
  });

  await page.goto('/people');
  const indicator = page.getByTestId('custom-export-layout-indicator');
  await expect(indicator).toBeVisible();
  await expect(indicator.locator('..')).toContainText('9. Export Layout');
  await expect(indicator.locator('..')).toHaveAttribute('title', /Clear All and Regenerate/);

  await page.goto('/shift-types');
  await expect(page.getByTestId('custom-export-layout-indicator')).toBeVisible();
});
