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

test('export formatting delete can be undone and redone', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed two formatting rules and confirm both cards are visible.
   * 2. Delete one rule from the Export Layout page.
   * 3. Undo to restore the deleted rule.
   * 4. Redo to remove it again.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'export formatting delete undo redo seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [
        { type: 'row', people: ['P1'], backgroundColor: '#111111' },
        { type: 'cell', people: ['P1'], dates: ['01'], shiftTypes: ['D'], backgroundColor: '#222222' },
      ],
    },
  });

  await page.goto('/export-layout');
  const cards = page.locator('[draggable="true"]');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('People: P1');
  await expect(cards.nth(1)).toContainText('Shift Types: D');

  await cards.nth(0).getByRole('button', { name: 'Delete' }).click();
  await expect(cards).toHaveCount(1);
  await expect(cards.nth(0)).toContainText('Shift Types: D');

  await page.getByRole('heading', { name: 'Export Layout', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('People: P1');
  await expect(cards.nth(1)).toContainText('Shift Types: D');

  await page.keyboard.press('Control+y');
  await expect(cards).toHaveCount(1);
  await expect(cards.nth(0)).toContainText('Shift Types: D');
});
