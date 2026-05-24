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

test('invalid YAML upload does not corrupt state and download still reflects the original state', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded YAML preview contains the original group name.
   * 2. Upload malformed YAML and confirm the preview remains unchanged.
   * 3. Download the current YAML.
   * 4. Confirm the downloaded content still reflects the original state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'invalid then download seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Original team' }],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'bad.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from('bad: [yaml', 'utf8'),
  });
  await expect(page.locator('pre')).toContainText('Team Alpha');

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const download = await downloadPromise;
  const content = await download.createReadStream();
  let yamlText = '';
  if (content) {
    for await (const chunk of content) {
      yamlText += chunk.toString();
    }
  }
  expect(yamlText).toContain('Team Alpha');
  expect(yamlText).not.toContain('Team Omega');
});
