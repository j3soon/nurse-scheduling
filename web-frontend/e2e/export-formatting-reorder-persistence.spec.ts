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

test('export formatting drag reorder persists after navigation', async ({ page }) => {
  /*
   * Steps:
   * 1. Add two formatting rules and confirm their original card order.
   * 2. Drag the second rule above the first using the real draggable cards.
   * 3. Navigate away and back, then confirm the reordered priority persisted.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'format reorder seed',
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

  await page.goto('/export-layout');
  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.locator('select').nth(1).selectOption('row');
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByTitle('Enter background color in hex').fill('#111111');
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.locator('select').nth(1).selectOption('column');
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByTitle('Enter background color in hex').fill('#222222');
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  const cards = page.locator('[draggable="true"]');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText('People: P1');
  await expect(cards.nth(1)).toContainText('Dates: 01');

  await cards.nth(1).dragTo(cards.nth(0));
  await expect(cards.nth(0)).toContainText('Dates: 01');
  await expect(cards.nth(1)).toContainText('People: P1');

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management', exact: true })).toBeVisible();
  await page.goto('/export-layout');
  const persistedCards = page.locator('[draggable="true"]');
  await expect(persistedCards.nth(0)).toContainText('Dates: 01');
  await expect(persistedCards.nth(1)).toContainText('People: P1');
});
