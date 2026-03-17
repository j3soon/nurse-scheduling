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

test('renaming people and groups updates downstream references across pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original person and group IDs are visible in the editor and downstream preference pages.
   * 2. Rename the person and then rename the group from the real people-management UI.
   * 3. Revisit downstream pages and confirm only the new IDs remain.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'rename cascade seed',
    dates: {
      range: {
        startDate: '2026-05-01',
        endDate: '2026-05-02',
      },
      groups: [],
    },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Secondary nurse', history: [] },
      ],
      groups: [
        { id: 'Team Alpha', members: ['P1', 'P2'], description: 'Main team' },
      ],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 3, description: 'request' },
      { type: 'shift count', person: ['Team Alpha'], countDates: ['ALL'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2, description: 'count rule' },
      { type: 'shift affinity', date: ['01'], people1: ['P1'], people2: ['Team Alpha'], shiftTypes: ['D'], weight: 1, description: 'affinity rule' },
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management' })).toBeVisible();

  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const groupsTable = page.getByRole('heading', { name: 'People Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(peopleTable.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(groupsTable.getByTitle('Team Alpha', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByText('Person: P1')).toBeVisible();
  await expect(page.getByText('Person: P1X')).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByText('People: Team Alpha')).toBeVisible();
  await expect(page.getByText('People: Team Omega')).toHaveCount(0);

  await page.goto('/shift-affinities');
  await expect(page.getByText('People 1: P1')).toBeVisible();
  await expect(page.getByText('People 2: Team Alpha')).toBeVisible();

  await page.goto('/people');

  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('P1X');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(peopleTable.getByText('1. P1X', { exact: true })).toBeVisible();
  await expect(peopleTable.getByText('1. P1', { exact: true })).toHaveCount(0);

  await groupsTable.locator('tr').filter({ has: page.getByText('Team Alpha', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Team Omega');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(groupsTable.getByTitle('Team Omega', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  await expect(page.getByText('Person: P1X')).toBeVisible();
  await expect(page.getByText('Person: P1', { exact: true })).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('count rule')).toBeVisible();
  await expect(page.getByText('People: Team Omega')).toBeVisible();
  await expect(page.getByText('People: Team Alpha', { exact: true })).toHaveCount(0);

  await page.goto('/shift-affinities');
  await expect(page.getByRole('heading', { name: 'Shift Affinities', exact: true })).toBeVisible();
  await expect(page.getByText('affinity rule')).toBeVisible();
  await expect(page.getByText('People 1: P1X')).toBeVisible();
  await expect(page.getByText('People 2: Team Omega')).toBeVisible();
  await expect(page.getByText('People 1: P1', { exact: true })).toHaveCount(0);
  await expect(page.getByText('People 2: Team Alpha', { exact: true })).toHaveCount(0);
});
