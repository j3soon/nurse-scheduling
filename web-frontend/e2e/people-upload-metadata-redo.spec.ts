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

test('people upload undo and redo preserve existing descriptions and history after reorder', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed people with descriptions and history, then upload a reordered list with one new person.
   * 2. Undo and redo the upload.
   * 3. Confirm the reordered state returns after redo.
   * 4. Verify the original people kept their descriptions and history after the redo.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people upload metadata redo seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: ['D'] },
        { id: 'P2', description: 'Secondary nurse', history: ['N'] },
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
    export: { formatting: [] },
  });

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P2', { exact: true })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P2\nP1\nP3\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(1);
  await expect(page.getByText('3. P3', { exact: true })).toBeVisible();

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await page.keyboard.press('Control+y');
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();

  await expect(page.getByText('1. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P3', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('description: Secondary nurse');
  await expect(page.locator('pre')).toContainText('description: Primary nurse');

  await page.goto('/shift-requests');
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentHistory.getByText(/Person: P2/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*N/)).toBeVisible();
  await expect(currentHistory.getByText(/Person: P1/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*D/)).toBeVisible();
});

test('people upload followed by shift-type deletion leaves no stale history IDs', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed history, then upload a reordered people list.
   * 2. Confirm the uploaded order is active.
   * 3. Delete the referenced shift type and confirm saved YAML has no stale history IDs.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people upload then shift delete seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: ['D'] },
        { id: 'P2', description: 'Secondary nurse', history: ['N'] },
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
    export: { formatting: [] },
  });

  await page.goto('/people');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P2\nP1\nP3\n', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(1);

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await page.keyboard.press('Control+y');

  await page.goto('/shift-types');
  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('1. D', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();

  await page.goto('/save-and-load');
  const yamlPreview = page.locator('pre');
  await expect(yamlPreview).toContainText('id: P1');
  await expect(yamlPreview).not.toContainText('history: [D]');
});
