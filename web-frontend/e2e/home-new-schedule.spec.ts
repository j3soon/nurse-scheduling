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

test('new schedule resets the app to the default seeded state from the home page flow', async ({ page }) => {
  /*
   * Steps:
   * 1. Visit the home page and confirm the reset entry point is visible.
   * 2. Trigger the New Schedule confirmation flow from the real home page.
   * 3. Confirm the default seeded state appears on downstream management pages.
   */
  await disableModalDialogs(page);

  await page.goto('/');
  await expect(page.getByRole('button', { name: 'New Schedule' })).toBeVisible();

  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management' })).toBeVisible();
  await expect(page.getByText('1. Person 1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. Person 2', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Group 1', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  await expect(page.getByRole('heading', { name: 'Shift Type Management' })).toBeVisible();
  await expect(page.getByText('1. D', { exact: true })).toBeVisible();
  await expect(page.getByText('2. D+', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Day', { exact: true }).first()).toBeVisible();
});

test('new schedule reset is undoable from downstream pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a distinctive schedule, then reset through the New Schedule flow.
   * 2. Confirm the seeded person disappeared and defaults are visible.
   * 3. Undo from a downstream page and confirm the seeded state returns.
   * 4. Redo and confirm the default reset state returns again.
  */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'undoable new schedule seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P9', description: 'Undoable nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'ZX', description: 'Undoable shift' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByText('1. Person 1', { exact: true })).toBeVisible();
  await expect(page.getByText('P9', { exact: true })).toHaveCount(0);

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('1. P9', { exact: true })).toBeVisible();
  await expect(page.getByText('1. Person 1', { exact: true })).toHaveCount(0);

  await page.keyboard.press('Control+y');
  await expect(page.getByText('1. Person 1', { exact: true })).toBeVisible();
  await expect(page.getByText('P9', { exact: true })).toHaveCount(0);
});

test('new schedule reset clears custom people history and export layout', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed custom history and export layout.
   * 2. Reset through the New Schedule flow.
   * 3. Confirm the saved YAML no longer contains the custom history or export extras.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'new schedule clears history export seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: ['D'] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [{ type: 'row', people: ['P1'], backgroundColor: '#111111' }],
      extraColumns: [{ type: 'count', header: 'Custom count', countDates: ['01'], countShiftTypes: ['D'] }],
    },
  });

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('history: [D]');
  await expect(page.locator('pre')).toContainText('Custom count');

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/save-and-load');
  const yamlPreview = page.locator('pre');
  await expect(yamlPreview).not.toContainText('Primary nurse');
  await expect(yamlPreview).not.toContainText('history: [D]');
  await expect(yamlPreview).not.toContainText('Custom count');
});
