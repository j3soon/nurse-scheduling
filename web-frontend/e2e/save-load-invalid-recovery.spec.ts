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

test('save-load editor recovers from invalid YAML and then saves successfully', async ({ page }) => {
  /*
   * Steps:
   * 1. Open save/load, confirm the original YAML is present, and enter edit mode.
   * 2. Break the YAML and confirm the page shows a validation error instead of saving.
   * 3. Fix the YAML in the same editor session and save it.
   * 4. Confirm the updated state is applied on a downstream page.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'invalid recovery seed',
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

  await page.getByRole('button', { name: 'Edit YAML' }).click();
  const textarea = page.locator('textarea');
  const originalYaml = await textarea.inputValue();
  await textarea.fill('people: [');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText(/unexpected end of the stream|unexpected end/i)).toBeVisible();

  await textarea.fill(originalYaml.replace('Team Alpha', 'Team Omega'));
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('pre')).toContainText('Team Omega');

  await page.goto('/people');
  await expect(page.getByTitle('Team Omega', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Alpha', { exact: true })).toHaveCount(0);
});
