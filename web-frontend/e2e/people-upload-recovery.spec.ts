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

test('people upload recovers from an invalid duplicate list and then accepts a valid list', async ({ page }) => {
  /*
   * Steps:
   * 1. Open People with a known initial order and confirm the original rows.
   * 2. Upload an invalid duplicate people list and confirm the page remains unchanged.
   * 3. Upload a valid list in the same session.
   * 4. Confirm the reordered and newly added people now appear.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people upload recovery seed',
    dates: { range: {}, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management', exact: true })).toBeVisible();
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('P3', { exact: true })).toHaveCount(0);

  const uploadInput = page.locator('input[type="file"]');
  await uploadInput.setInputFiles({
    name: 'people-invalid.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P1\nP1\n', 'utf8'),
  });

  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0]).toContain('Duplicate person name "P1"');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('P3', { exact: true })).toHaveCount(0);

  await uploadInput.setInputFiles({
    name: 'people-valid.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P3\nP1\n', 'utf8'),
  });

  await expect.poll(() => dialogs.length).toBe(2);
  expect(dialogs[1]).toContain('Successfully uploaded 2 people');
  await expect(page.getByText('1. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P2', { exact: true })).toBeVisible();
});
