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

test('renamed people and groups survive a save-load roundtrip', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original person and group names are visible before renaming.
   * 2. Rename both through the real People page UI.
   * 3. Capture the resulting YAML from Save and Load.
   * 4. Upload that YAML back and confirm the renamed references persist.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'rename roundtrip seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [{ id: 'Team Alpha', members: ['P1', 'P2'], description: 'Main team' }],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 3 },
      { type: 'shift count', person: ['Team Alpha'], countDates: ['ALL'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const groupsTable = page.getByRole('heading', { name: 'People Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(peopleTable.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(groupsTable.getByTitle('Team Alpha', { exact: true })).toBeVisible();

  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('P1X');
  await page.getByRole('button', { name: 'Update' }).click();
  await groupsTable.locator('tr').filter({ has: page.getByText('Team Alpha', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Team Omega');
  await page.getByRole('button', { name: 'Update' }).click();

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('P1X');
  await expect(page.locator('pre')).toContainText('Team Omega');
  const yamlText = await page.locator('pre').textContent();

  await page.locator('input[type="file"]').setInputFiles({
    name: 'rename-roundtrip.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await page.goto('/shift-requests');
  await expect(page.getByText('Person: P1X')).toBeVisible();
  await expect(page.getByText('Person: P1', { exact: true })).toHaveCount(0);
  await page.goto('/shift-counts');
  await expect(page.getByText('People: Team Omega')).toBeVisible();
  await expect(page.getByText('People: Team Alpha', { exact: true })).toHaveCount(0);
});
