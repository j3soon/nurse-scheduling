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

test('uploading people reorders and adds rows that then appear in save-load YAML', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the People page starts without the uploaded person and with the original row order.
   * 2. Upload a newline-separated people list through the real People page control.
   * 3. Confirm the row order updates on the page and the same order is reflected in save/load YAML.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'people upload seed',
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

  await page.locator('input[type="file"]').setInputFiles({
    name: 'people.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('P3\nP1\n', 'utf8'),
  });

  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0]).toContain('Successfully uploaded 2 people');

  await expect(page.getByText('1. P3', { exact: true })).toBeVisible();
  await expect(page.getByText('2. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('3. P2', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await page.reload();
  await expect(page.locator('pre')).toContainText('P3');
  const yamlText = await page.locator('pre').textContent();
  const p3Index = (yamlText ?? '').indexOf('id: P3');
  const p1Index = (yamlText ?? '').indexOf('id: P1');
  const p2Index = (yamlText ?? '').indexOf('id: P2');
  expect(p3Index).toBeGreaterThanOrEqual(0);
  expect(p1Index).toBeGreaterThan(p3Index);
  expect(p2Index).toBeGreaterThan(p1Index);
});
