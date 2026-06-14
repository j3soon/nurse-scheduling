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

test('dates page keeps generated date items read-only while group controls remain available', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a date range with one manual group and confirm both tables render.
   * 2. Confirm the page does not expose Add Date or date-row edit/delete controls.
   * 3. Confirm group-level controls still exist on the same page.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'dates read only seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-02' },
      groups: [{ id: 'Special Dates', members: ['01'], description: 'Manual group' }],
    },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/dates');
  await expect(page.getByRole('heading', { name: 'Date Management', exact: true })).toBeVisible();
  await expect(page.getByText('Duration: 2 days')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add Date' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Add Group' })).toBeVisible();

  const datesTable = page.getByRole('heading', { name: 'Dates', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const groupsTable = page.getByRole('heading', { name: 'Dates Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');

  await expect(datesTable.getByText('01', { exact: true })).toBeVisible();
  await expect(datesTable.getByRole('button', { name: 'Edit' })).toHaveCount(0);
  await expect(datesTable.getByRole('button', { name: 'Delete' })).toHaveCount(0);

  await expect(groupsTable.getByText('Special Dates', { exact: true })).toBeVisible();
  await expect(groupsTable.getByRole('button', { name: 'Edit' })).toBeVisible();

  await groupsTable.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByText('May 2026', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Previous month' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Next month' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '01' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Unavailable 2026-05-03' })).toBeDisabled();
});

test('dates page edits full-month date-group members with a calendar', async ({ page }) => {
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'date group calendar seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-31' },
      groups: [{ id: 'Special Dates', members: ['01'], description: 'Manual group' }],
    },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
    export: { formatting: [] },
  });

  await page.goto('/dates');
  const groupsTable = page.getByRole('heading', { name: 'Dates Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const specialDatesRow = groupsTable.getByTitle('Special Dates').locator('xpath=ancestor::tr');
  await specialDatesRow.getByRole('button', { name: 'Edit' }).click();

  await expect(page.getByRole('heading', { name: 'Edit Group' })).toBeVisible();
  await expect(page.getByText('May 2026', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '01' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'List view' }).click();
  await page.getByLabel('02').click();
  await page.getByRole('button', { name: 'Calendar view' }).click();
  await expect(page.getByRole('button', { name: '01' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: '02' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Update' }).click();

  await expect(specialDatesRow).toContainText('2 members');
  await expect(specialDatesRow).toContainText('01');
  await expect(specialDatesRow).toContainText('02');
});
