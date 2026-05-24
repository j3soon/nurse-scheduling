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

test('download after editing YAML reflects the saved edited state', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original YAML contains the seeded group name.
   * 2. Edit and save the YAML with a renamed group.
   * 3. Download the YAML through the real control.
   * 4. Confirm the downloaded content reflects the edited state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'edit download seed',
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
  await page.getByRole('button', { name: 'Edit YAML' }).click();
  const textarea = page.locator('textarea');
  const originalYaml = await textarea.inputValue();
  await textarea.fill(originalYaml.replace('Team Alpha', 'Team Omega'));
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('pre')).toContainText('Team Omega');

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
  expect(yamlText).toContain('Team Omega');
  expect(yamlText).not.toContain('Team Alpha');
});
