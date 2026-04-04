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
import { seedSchedulingState } from './helpers';

test('people upload preserves unmentioned existing people at the tail in their original order', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original people order.
   * 2. Upload a file that reorders only a subset of the people.
   * 3. Confirm the requested subset moves to the front.
   * 4. Confirm the unmentioned trailing people keep their original relative order.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people tail order seed',
    dates: { range: {}, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'One', history: [] },
        { id: 'P2', description: 'Two', history: [] },
        { id: 'P3', description: 'Three', history: [] },
        { id: 'P4', description: 'Four', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('4. P4', { exact: true })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P3\nP1\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(1);

  await expect(page.getByText('1. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('4. P4', { exact: true })).toBeVisible();
});
