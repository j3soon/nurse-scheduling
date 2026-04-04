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

test('partial YAML upload replaces old sections instead of preserving stale group data', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original seeded preview contains a people group.
   * 2. Upload a valid YAML state without any people groups.
   * 3. Confirm the preview now contains the new person and no longer contains the old group.
   * 4. Verify the downstream People page also no longer shows the stale group.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'partial replacement seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Old group' }],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  const yamlWithoutGroups = `apiVersion: test\ndescription: replacement state\ndates:\n  range:\n    startDate: 2026-06-01\n    endDate: 2026-06-01\n  groups: []\npeople:\n  items:\n    - id: P2\n      description: Replacement nurse\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: N\n      description: Night\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('Team Alpha');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'replacement.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlWithoutGroups, 'utf8'),
  });

  await expect(page.locator('pre')).toContainText('replacement state');
  await expect(page.locator('pre')).toContainText('P2');
  await expect(page.locator('pre')).not.toContainText('Team Alpha');

  await page.goto('/people');
  await expect(page.getByText('1. P2', { exact: true })).toBeVisible();
  await expect(page.getByText('Team Alpha', { exact: true })).toHaveCount(0);
});
