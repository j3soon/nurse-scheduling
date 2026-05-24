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

test('export formatting reorder and edit can be undone and redone independently', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed two formatting rules and confirm their initial order.
   * 2. Reorder the rules, then edit the moved rule to add a bottom border.
   * 3. Undo once to remove only the edit while preserving the reordered priority.
   * 4. Undo again to restore the original order, then redo both steps.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'format history seed',
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
    export: {
      formatting: [
        { type: 'row', people: ['P1'], backgroundColor: '#111111' },
        { type: 'column', dates: ['01'], backgroundColor: '#222222' },
      ],
    },
  });

  await page.goto('/export-layout');
  const cards = page.locator('[draggable="true"]');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('People: P1');
  await expect(cards.nth(1)).toContainText('Dates: 01');

  await cards.nth(1).dragTo(cards.nth(0));
  await expect(cards.nth(0)).toContainText('Dates: 01');
  await expect(cards.nth(1)).toContainText('People: P1');

  await cards.nth(0).getByRole('button', { name: 'Edit' }).click();
  await page.getByTitle('Enter bottom border color in hex').fill('#333333');
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(cards.nth(0)).toContainText('Dates: 01');
  await expect(cards.nth(0)).toContainText('Bottom Border: #333333');

  await page.getByRole('heading', { name: 'Export Layout', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(cards.nth(0)).toContainText('Dates: 01');
  await expect(cards.nth(0)).not.toContainText('Bottom Border: #333333');
  await expect(cards.nth(1)).toContainText('People: P1');

  await page.keyboard.press('Control+z');
  await expect(cards.nth(0)).toContainText('People: P1');
  await expect(cards.nth(1)).toContainText('Dates: 01');

  await page.keyboard.press('Control+y');
  await expect(cards.nth(0)).toContainText('Dates: 01');
  await expect(cards.nth(1)).toContainText('People: P1');

  await page.keyboard.press('Control+y');
  await expect(cards.nth(0)).toContainText('Dates: 01');
  await expect(cards.nth(0)).toContainText('Bottom Border: #333333');
});
