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

test('people upload can retry the same filename after failure and then recover with valid content', async ({ page }) => {
  /*
   * Steps:
   * 1. Open People with a known initial order and confirm the original rows.
   * 2. Upload one invalid duplicate file and confirm the page stays unchanged.
   * 3. Upload the same filename again with invalid content to confirm the browser path retries it.
   * 4. Upload the same filename with valid content and confirm recovery.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'same file retry seed',
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
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  const uploadInput = page.locator('input[type="file"]');

  await uploadInput.setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P1\nP1\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0]).toContain('Duplicate person name "P1"');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();

  await uploadInput.setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P2\nP2\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(2);
  expect(dialogs[1]).toContain('Duplicate person name "P2"');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();

  await uploadInput.setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P2\nP3\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(3);
  expect(dialogs[2]).toContain('Successfully uploaded 2 people');
  await expect(page.getByText('1. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P1', { exact: true })).toBeVisible();
});
