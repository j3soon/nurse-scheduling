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

test('reset followed by upload restores downstream pages, not just the YAML preview', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a mixed state and capture its YAML from Save and Load.
   * 2. Reset the app through New Schedule and confirm the seeded entities disappear downstream.
   * 3. Upload the captured YAML.
   * 4. Verify People, Shift Types, and Shift Requests all reflect the restored state.
   */
  await disableModalDialogs(page);
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
  });
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'reset restore downstream seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'Restore Person', description: 'Restored person', history: [] }],
      groups: [{ id: 'Restore Group', members: ['Restore Person'], description: 'Restored group' }],
      history: [],
    },
    shiftTypes: { items: [{ id: 'RX', description: 'Restore Shift' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['Restore Person'], date: ['01'], shiftType: ['RX'], weight: 2 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Restore Person');
  const yamlText = await page.locator('pre').textContent();

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByText('Restore Person', { exact: true })).toHaveCount(0);
  await page.goto('/shift-types');
  await expect(page.getByText('RX', { exact: true })).toHaveCount(0);

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'restore.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await expect.poll(() => dialogs.some(message => message.includes('YAML file loaded successfully!'))).toBe(true);

  await page.goto('/people');
  await expect(page.locator('span').filter({ hasText: 'Restore Person' }).first()).toBeVisible();
  await expect(page.getByTitle('Restore Group', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  await expect(page.getByText('RX', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByText('Person: Restore Person')).toBeVisible();
  await expect(page.getByText(/Shift Type:\s*RX/)).toBeVisible();
});
