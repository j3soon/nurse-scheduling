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

test('renaming shift types and shift type groups updates downstream references', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original shift type and shift type group IDs are visible in the editor and downstream pages.
   * 2. Rename the shift type and then rename the shift type group from the real management UI.
   * 3. Revisit downstream pages and confirm only the renamed IDs remain.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift type rename seed',
    dates: {
      range: {
        startDate: '2026-05-01',
        endDate: '2026-05-01',
      },
      groups: [],
    },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [
        { id: 'Day', members: ['D'], description: 'Day shifts' },
      ],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 3, description: 'request rule' },
      { type: 'shift count', person: ['P1'], countDates: ['01'], countShiftTypes: ['Day'], expression: 'x >= T', target: 1, weight: 2, description: 'count rule' },
      { type: 'shift affinity', date: ['01'], people1: ['P1'], people2: ['ALL'], shiftTypes: ['D'], weight: 1, description: 'affinity rule' },
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/shift-types');
  await expect(page.getByRole('heading', { name: 'Shift Type Management' })).toBeVisible();

  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const shiftTypeGroupsTable = page.getByRole('heading', { name: 'Shift Types Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const dayGroupRow = shiftTypeGroupsTable.locator('tr').filter({ has: page.getByText('Day', { exact: true }) }).first();
  await expect(shiftTypesTable.getByText('1. D', { exact: true })).toBeVisible();
  await expect(dayGroupRow).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByText('Shift Type: D')).toBeVisible();
  await expect(page.getByText('Shift Type: DX')).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByText('Count Shift Types: Day')).toBeVisible();
  await expect(page.getByText('Count Shift Types: Daytime')).toHaveCount(0);

  await page.goto('/shift-affinities');
  await expect(page.getByText('Shift Types: D')).toBeVisible();
  await expect(page.getByText('Shift Types: DX')).toHaveCount(0);

  await page.goto('/shift-types');

  await shiftTypesTable.locator('tr').filter({ has: page.getByText('1. D', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter shift type ID').fill('DX');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(shiftTypesTable.getByText('1. DX', { exact: true })).toBeVisible();

  await dayGroupRow.getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter group ID').fill('Daytime');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(
    shiftTypeGroupsTable.locator('tr').filter({ has: page.getByText('Daytime', { exact: true }) }).first()
  ).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  await expect(page.getByText('Shift Type: DX')).toBeVisible();
  await expect(page.getByText('Shift Type: D', { exact: true })).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('Count Shift Types: Daytime')).toBeVisible();
  await expect(page.getByText('Count Shift Types: Day', { exact: true })).toHaveCount(0);

  await page.goto('/shift-affinities');
  await expect(page.getByRole('heading', { name: 'Shift Affinities', exact: true })).toBeVisible();
  await expect(page.getByText('Shift Types: DX')).toBeVisible();
  await expect(page.getByText('Shift Types: D', { exact: true })).toHaveCount(0);
});

test('renaming and deleting shift types keeps people history coherent in UI and YAML', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed ordered people history with an older D entry between A and N.
   * 2. Rename D to DX and confirm history is renamed in the summary and YAML.
   * 3. Delete DX and confirm the deleted history entry is replaced with an empty slot.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift history rename delete seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: ['A', 'D', 'N'] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'A', description: 'Admin' },
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  const currentHistory = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Current People History' }) }).first();
  await expect(currentHistory.getByText(/H-3:\s*A/)).toBeVisible();
  await expect(currentHistory.getByText(/H-2:\s*D/)).toBeVisible();
  await expect(currentHistory.getByText(/H-1:\s*N/)).toBeVisible();

  await page.goto('/shift-types');
  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('2. D', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter shift type ID').fill('DX');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(shiftTypesTable.getByText('2. DX', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(currentHistory.getByText(/H-2:\s*DX/)).toBeVisible();

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('history: [A, DX, N]');
  await expect(page.locator('pre')).not.toContainText('history: [A, D, N]');

  await page.goto('/shift-types');
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('2. DX', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();

  await page.goto('/shift-requests');
  await expect(currentHistory.getByText(/H-1:\s*N/)).toBeVisible();
  await expect(currentHistory.getByText(/H-2:\s*$/)).toBeVisible();
  await expect(currentHistory.getByText(/H-3:\s*A/)).toBeVisible();
  await expect(currentHistory.getByText(/DX/)).toHaveCount(0);

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText("history: [A, '', N]");
  await expect(page.locator('pre')).not.toContainText('DX');
});

test('optimize payload reflects empty replacement in people history after shift-type deletion', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed history where D is older than N.
   * 2. Delete D through the shift-type page.
   * 3. Run Optimize and assert the submitted YAML keeps the empty replacement slot.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'shift history optimize trim seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: ['A', 'D', 'N'] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'A', description: 'Admin' },
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['N'], weight: 1 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-types');
  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('2. D', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();

  let submittedBody = '';
  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();

  expect(submittedBody).toContain("history: [A, '', N]");
  expect(submittedBody).not.toContain('id: D');
});
