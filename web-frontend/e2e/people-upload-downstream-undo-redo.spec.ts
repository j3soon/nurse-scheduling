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

test('people bulk upload updates downstream routes and can be undone and redone', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed people and a single downstream date matrix, then confirm the original state.
   * 2. Upload a reordered list that adds one new person.
   * 3. Confirm both the People page and Shift Requests reflect the uploaded state.
   * 4. Undo and redo the upload to verify downstream route state tracks the bulk change.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people downstream upload undo redo seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 01')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P2 on date 01')).toBeVisible();
  await expect(page.getByTitle('Click to update preferences for P3 on date 01')).toHaveCount(0);

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P3\nP1\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(1);
  await expect(page.getByText('1. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P2', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P3 on date 01')).toBeVisible();

  await page.getByRole('heading', { name: 'Shift Requests', exact: true }).click();
  await page.keyboard.press('Control+z');
  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('P3', { exact: true })).toHaveCount(0);
  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P3 on date 01')).toHaveCount(0);

  await page.getByRole('heading', { name: 'Shift Requests', exact: true }).click();
  await page.keyboard.press('Control+y');
  await page.goto('/people');
  await expect(page.getByText('1. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P2', { exact: true })).toBeVisible();
  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P3 on date 01')).toBeVisible();
});
