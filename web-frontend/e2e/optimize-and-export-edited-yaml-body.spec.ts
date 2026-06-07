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
import { disableModalDialogs, mockOptimizeAndExport, seedSchedulingState } from './helpers';

test('optimize request body reflects YAML-edited state', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded YAML contains the old group name.
   * 2. Edit YAML through Save and Load and save a renamed group.
   * 3. Trigger optimize with a mocked backend.
   * 4. Confirm the posted yaml_content contains the renamed group and not the old one.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize yaml body seed',
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
  const editedYaml = ((await textarea.inputValue()) || '').replace('Team Alpha', 'Team Omega');
  await textarea.fill(editedYaml);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('pre')).toContainText('Team Omega');

  let submittedBody = '';
  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await downloadPromise;
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  expect(submittedBody).toContain('Team Omega');
  expect(submittedBody).not.toContain('Team Alpha');
});
