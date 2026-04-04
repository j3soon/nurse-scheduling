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

test('save-load copy and download expose the current YAML through real UI controls', async ({ page, context }) => {
  /*
   * Steps:
   * 1. Open Save and Load with a known YAML payload and confirm the original text is visible.
   * 2. Click Copy and confirm the UI enters the copied state.
   * 3. Click Download and confirm a browser download is emitted.
   * 4. Confirm the downloaded file name and contents match the current YAML.
   */
  await disableModalDialogs(page);
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'copy download seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Original team' }],
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
  await expect(page.getByRole('heading', { name: 'Save and Load' })).toBeVisible();
  await expect(page.locator('pre')).toContainText('Team Alpha');

  await page.getByRole('button', { name: 'Copy' }).click();
  await expect(page.getByRole('button', { name: 'Copied!' })).toBeVisible();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^nurse-scheduling-\d{4}-\d{2}-\d{2}\.yaml$/);
  const content = await download.createReadStream();
  let yamlText = '';
  if (content) {
    for await (const chunk of content) {
      yamlText += chunk.toString();
    }
  }
  expect(yamlText).toContain('Team Alpha');
  expect(yamlText).toContain('apiVersion: test');
});
