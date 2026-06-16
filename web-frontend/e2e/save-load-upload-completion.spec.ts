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

test('save-load upload waits for completion dialogs before downstream state is asserted', async ({ page }) => {
  /*
   * Steps:
   * 1. Capture a valid YAML snapshot from a seeded state, then reset the app and confirm the original state is gone.
   * 2. Upload that YAML through the real save/load control and wait for the completion dialog.
   * 3. Verify the restored state only after the upload-completion path has fired.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'upload completion seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Main team' }],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Team Alpha');
  const yamlText = await page.locator('pre').textContent();
  expect(yamlText).toContain('Team Alpha');

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByTitle('Team Alpha', { exact: true })).toHaveCount(0);

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'restore.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await expect.poll(() => dialogs.filter(message => message.includes('YAML file loaded successfully!')).length).toBe(1);
  expect(dialogs.find(message => message.includes('YAML file loaded successfully!'))).toBeDefined();
  await expect(page.locator('pre')).toContainText('Team Alpha');

  await page.goto('/people');
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();
});
