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
import { seedSchedulingState, waitForStoredCurrentSchedulingData } from './helpers';

test('save-load YAML preview reflects uploaded state after a page refresh', async ({ page }) => {
  /*
   * Steps:
   * 1. Capture a valid YAML snapshot from a seeded state, then reset and confirm the preview no longer shows that state.
   * 2. Upload the YAML back through save/load and wait for the upload-completion dialog.
   * 3. Refresh the page and confirm the YAML preview now matches the uploaded state.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'preview refresh seed',
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

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).not.toContainText('Team Alpha');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'restore.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await expect.poll(() => dialogs.filter(message => message.includes('YAML file loaded successfully!')).length).toBe(1);
  expect(dialogs.find(message => message.includes('YAML file loaded successfully!'))).toBeDefined();
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await waitForStoredCurrentSchedulingData(page, 'Team Alpha');
  await page.reload();
  await expect(page.locator('pre')).toContainText('Team Alpha');
});
