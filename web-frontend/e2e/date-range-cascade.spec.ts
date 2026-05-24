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

test('shrinking the date range removes stale date references from downstream pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm downstream pages currently reference the second date before any edit.
   * 2. Shrink the managed date range from two days down to one day.
   * 3. Revisit downstream pages and confirm references to the removed date are gone.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'date shrink seed',
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
      ],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [
        { id: 'D', description: 'Day' },
      ],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['02'], shiftType: ['D'], weight: 2, description: 'second-day request' },
      { type: 'shift count', person: ['P1'], countDates: ['01', '02'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2, description: 'date window count' },
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('date window count')).toBeVisible();
  await expect(page.getByText('Count Dates: 01, 02')).toBeVisible();
  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 02')).toBeVisible();

  await page.goto('/dates');
  await expect(page.getByRole('heading', { name: 'Date Management' })).toBeVisible();
  await expect(page.getByText('Duration: 2 days')).toBeVisible();
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-05-01');
  await page.locator('#endDate').fill('2026-05-01');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('Duration: 1 days')).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByRole('heading', { name: 'Shift Requests', exact: true })).toBeVisible();
  await expect(page.getByText('second-day request')).toHaveCount(0);
  await expect(page.getByText('Date: 02')).toHaveCount(0);
  await expect(page.getByTitle('Click to update preferences for P1 on date 02')).toHaveCount(0);

  await page.goto('/shift-counts');
  await expect(page.getByRole('heading', { name: 'Shift Counts', exact: true })).toBeVisible();
  await expect(page.getByText('date window count')).toBeVisible();
  await expect(page.getByText('Count Dates: 01')).toBeVisible();
  await expect(page.getByText('Count Dates: 01, 02')).toHaveCount(0);
});

test('shrinking the date range removes stale date references from export layout state', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed export formatting and count columns that reference both dates.
   * 2. Shrink the date range to remove the second date.
   * 3. Confirm Save and Load YAML keeps date 01 and drops date 02 from export layout.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'date export cascade seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-02' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [
        { type: 'column', dates: ['01', '02'], backgroundColor: '#111111' },
        { type: 'cell', people: ['P1'], dates: ['02'], shiftTypes: ['D'], backgroundColor: '#222222' },
      ],
      extraColumns: [
        { type: 'count', header: 'Both days', countDates: ['01', '02'], countShiftTypes: ['D'] },
        { type: 'count', header: 'Second day only', countDates: ['02'], countShiftTypes: ['D'] },
      ],
    },
  });

  await page.goto('/dates');
  await expect(page.getByText('Duration: 2 days')).toBeVisible();
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-05-01');
  await page.locator('#endDate').fill('2026-05-01');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('Duration: 1 days')).toBeVisible();

  await page.goto('/save-and-load');
  const yamlPreview = page.locator('pre');
  await expect(yamlPreview).toContainText("dates: ['01']");
  await expect(yamlPreview).toContainText("countDates: ['01']");
  await expect(yamlPreview).not.toContainText("dates: ['02']");
  await expect(yamlPreview).not.toContainText("countDates: ['02']");
  await expect(yamlPreview).not.toContainText('Second day only');
});

test('date identifier format changes remove stale export layout references', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed same-month date IDs referenced from export layout.
   * 2. Change the range to cross a month boundary, which changes generated date IDs.
   * 3. Confirm old export layout references are removed from Save and Load YAML.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'date id transition export seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-02' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: {
      formatting: [
        { type: 'column', dates: ['01', '02'], backgroundColor: '#111111' },
        { type: 'cell', people: ['P1'], dates: ['01'], shiftTypes: ['D'], backgroundColor: '#222222' },
      ],
      extraColumns: [
        { type: 'count', header: 'Old dates', countDates: ['01', '02'], countShiftTypes: ['D'] },
      ],
    },
  });

  await page.goto('/dates');
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill('2026-05-31');
  await page.locator('#endDate').fill('2026-06-01');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('Duration: 2 days')).toBeVisible();

  await page.goto('/save-and-load');
  const yamlPreview = page.locator('pre');
  await expect(yamlPreview).not.toContainText("dates: ['01'");
  await expect(yamlPreview).not.toContainText('countDates:');
  await expect(yamlPreview).not.toContainText('Old dates');
});
