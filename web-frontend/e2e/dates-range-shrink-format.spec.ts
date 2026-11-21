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
import { disableModalDialogs, seedScheduleSpecState } from './helpers';

test('shrinking a month-spanning range preserves requests for retained dates', async ({ page }) => {
  await disableModalDialogs(page);
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'range shrink format seed',
    dates: { range: { startDate: '2026-05-31', endDate: '2026-06-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['05-31', '06-01'], shiftType: ['D'], weight: 3 },
    ],
    export: { formatting: [] },
  });

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 05-31')).toHaveText('D (+3)');
  await expect(page.getByTitle('Click to update preferences for P1 on date 06-01')).toHaveText('D (+3)');

  await page.goto('/dates');
  await page.getByRole('button', { name: /Set Date Range|Edit Date Range/ }).click();
  await page.locator('#startDate').fill('2026-05-31');
  await page.locator('#endDate').fill('2026-05-31');
  await page.getByRole('button', { name: /Apply|Update/ }).click();
  await expect(page.getByText('Duration: 1 days')).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByTitle('Click to update preferences for P1 on date 31')).toHaveText('D (+3)');
  await expect(page.getByTitle('Click to update preferences for P1 on date 05-31')).toHaveCount(0);
});

test('requires renaming a legacy group before its ID collides with a generated date', async ({ page }) => {
  await disableModalDialogs(page);
  await seedScheduleSpecState(page, {
    apiVersion: 'alpha',
    description: '',
    dates: {
      range: { startDate: '2026-11-01', endDate: '2026-11-03' },
      groups: [{ id: '2026-11-02', description: '', members: ['03'] }],
    },
    people: { items: [], groups: [], history: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/dates');
  await page.getByRole('button', { name: 'Set Date Range', exact: true }).click();
  await page.locator('#endDate').fill('2027-01-01');
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByText('Rename date group 2026-11-02 before changing the range.')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByText('Duration: 3 days')).toBeVisible();

  const groupRow = page.getByRole('row')
    .filter({ has: page.getByRole('button', { name: 'Edit', exact: true }) })
    .filter({ has: page.getByTitle('2026-11-02', { exact: true }) });
  await groupRow.getByRole('button', { name: 'Edit', exact: true }).click();
  const id = page.getByPlaceholder('Enter group ID', { exact: true });
  await id.fill('3~4');
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByText('A date group ID cannot look like a date or date range expression.')).toBeVisible();
  await id.fill('Special days');
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByTitle('Special days', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Set Date Range', exact: true }).click();
  await page.locator('#endDate').fill('2027-01-01');
  await page.getByRole('button', { name: 'Update', exact: true }).click();
  await expect(page.getByText('Duration: 62 days')).toBeVisible();
});
