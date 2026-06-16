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
import { disableModalDialogs, disableOptimizeAnonymization, mockOptimizeAndExport, seedSchedulingState } from './helpers';

test('export layout references cascade through entity rename, delete, undo, and redo', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed export formatting and count-layout entries that reference people, dates, and shift types.
   * 2. Rename a person and shift type, then delete the renamed person.
   * 3. Confirm Save and Load YAML reflects the cascade, then undo and redo the delete.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'export layout cascade seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Backup nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [
        { type: 'row', people: ['P1', 'P2'], backgroundColor: '#111111' },
        { type: 'cell', people: ['P1'], dates: ['01'], shiftTypes: ['D'], backgroundColor: '#222222' },
      ],
      extraRows: [
        { type: 'count', header: 'P1 day count', countPeople: ['P1'], countShiftTypes: ['D'] },
      ],
      extraColumns: [
        { type: 'count', header: 'Day count', countDates: ['01'], countShiftTypes: ['D'] },
      ],
    },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(peopleTable.getByText('1. P1', { exact: true })).toBeVisible();
  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('P1X');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(peopleTable.getByText('1. P1X', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(shiftTypesTable.getByText('1. D', { exact: true })).toBeVisible();
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('1. D', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter shift type ID').fill('DX');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(shiftTypesTable.getByText('1. DX', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('P1X');
  await expect(page.locator('pre')).toContainText('DX');
  await expect(page.locator('pre')).not.toContainText('countPeople: [P1]');
  await expect(page.locator('pre')).not.toContainText('countShiftTypes: [D]');

  await page.goto('/people');
  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1X', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();
  await expect(peopleTable.getByText('1. P2', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('people: [P2]');
  await expect(page.locator('pre')).not.toContainText('P1X');
  await expect(page.locator('pre')).not.toContainText('P1 day count');

  await page.getByRole('heading', { name: 'Save and Load', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.locator('pre')).toContainText('P1X');
  await expect(page.locator('pre')).toContainText('P1 day count');

  await page.keyboard.press('Control+y');
  await expect(page.locator('pre')).not.toContainText('P1X');
  await expect(page.locator('pre')).not.toContainText('P1 day count');
});

test('export layout extra rows and columns cascade through entity deletion', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed export extra rows/columns with mixed people and shift-type references.
   * 2. Delete one person and one shift type.
   * 3. Confirm partially affected rules are narrowed and fully stale rules are removed.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'export extra layout cascade seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: [] },
        { id: 'P2', description: 'Backup nurse', history: [] },
      ],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [],
      extraColumns: [
        {
          type: 'count',
          header: 'All shifts',
          countDates: ['01'],
          countShiftTypes: ['D', 'N'],
          countShiftTypeCoefficients: [['D', 2], ['N', 3]],
        },
        { type: 'count', header: 'Night only', countDates: ['01'], countShiftTypes: ['N'] },
      ],
      extraRows: [
        { type: 'count', header: 'All people', countPeople: ['P1', 'P2'], countShiftTypes: ['D'] },
        { type: 'count', header: 'P1 only', countPeople: ['P1'], countShiftTypes: ['D'] },
      ],
    },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(peopleTable.getByText('1. P1', { exact: true })).toBeVisible();
  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();
  await expect(peopleTable.getByText('1. P2', { exact: true })).toBeVisible();

  await page.goto('/shift-types');
  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(shiftTypesTable.getByText('2. N', { exact: true })).toBeVisible();
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('2. N', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();

  await page.goto('/save-and-load');
  const yamlPreview = page.locator('pre');
  await expect(yamlPreview).toContainText('header: All shifts');
  await expect(yamlPreview).toContainText('countShiftTypes: [D]');
  await expect(yamlPreview).toContainText('countShiftTypeCoefficients');
  await expect(yamlPreview).toContainText('[D, 2]');
  await expect(yamlPreview).not.toContainText('[N, 3]');
  await expect(yamlPreview).toContainText('header: All people');
  await expect(yamlPreview).toContainText('countPeople: [P2]');
  await expect(yamlPreview).not.toContainText('Night only');
  await expect(yamlPreview).not.toContainText('P1 only');
  await expect(yamlPreview).not.toContainText('countPeople: [P1]');
  await expect(yamlPreview).not.toContainText('countShiftTypes: [N]');
});

test('optimize payload stays free of stale IDs after delete cascade', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed preferences, history, and export layout that reference P1 and N.
   * 2. Delete P1 and N through the real management pages.
   * 3. Run Optimize with a mocked backend and inspect the submitted YAML.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize stale cascade seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [
        { id: 'P1', description: 'Primary nurse', history: ['N'] },
        { id: 'P2', description: 'Backup nurse', history: ['D'] },
      ],
      groups: [],
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
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['N'], weight: 2 },
      { type: 'shift request', person: ['P2'], date: ['01'], shiftType: ['D'], weight: 1 },
    ],
    export: {
      formatting: [
        { type: 'row', people: ['P1', 'P2'], backgroundColor: '#111111' },
        { type: 'cell', people: ['P1'], dates: ['01'], shiftTypes: ['N'], backgroundColor: '#222222' },
      ],
      extraRows: [
        { type: 'count', header: 'P1 nights', countPeople: ['P1'], countShiftTypes: ['N'] },
      ],
    },
  });

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(peopleTable.getByText('1. P1', { exact: true })).toBeVisible();
  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();

  await page.goto('/shift-types');
  const shiftTypesTable = page.getByRole('heading', { name: 'Shift Types', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await expect(shiftTypesTable.getByText('2. N', { exact: true })).toBeVisible();
  await shiftTypesTable.locator('tr').filter({ has: page.getByText('2. N', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();

  let submittedBody = '';
  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  await disableOptimizeAnonymization(page);
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();

  expect(submittedBody).toContain('P2');
  expect(submittedBody).toContain('id: D');
  expect(submittedBody).not.toContain('id: P1');
  expect(submittedBody).not.toContain('person: [P1]');
  expect(submittedBody).not.toContain('people: [P1]');
  expect(submittedBody).not.toContain('id: N');
  expect(submittedBody).not.toContain('shiftType: [N]');
  expect(submittedBody).not.toContain('shiftTypes: [N]');
  expect(submittedBody).not.toContain('countShiftTypes: [N]');
  expect(submittedBody).not.toContain('P1 nights');
});
