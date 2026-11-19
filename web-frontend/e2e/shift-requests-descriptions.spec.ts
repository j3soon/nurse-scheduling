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

import yaml from 'js-yaml';
import { expect, test } from './test';
import { seedScheduleSpecState } from './helpers';

const scheduleSpec = {
  apiVersion: 'test',
  description: '',
  dates: { range: { startDate: '2026-05-01', endDate: '2026-05-03' }, groups: [] },
  people: {
    items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
    groups: [{ id: 'Team', description: '', members: ['P1', 'P2'] }],
    history: [],
  },
  shiftTypes: {
    items: [{ id: 'D', description: 'Day shift' }, { id: 'N', description: 'Night shift' }],
    groups: [],
  },
  export: { formatting: [] },
};

test('edits one date of a people-group request and compacts it again when descriptions match', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await seedScheduleSpecState(page, {
    ...scheduleSpec,
    preferences: [
      { type: 'shift request', person: ['Team'], date: ['01', '02', '03'], shiftType: ['D'], weight: 2, description: 'Shared note' },
      { type: 'shift request', person: ['Team'], date: ['02'], shiftType: ['N'], weight: -1, description: 'Night note' },
    ],
  });

  await page.goto('/shift-requests');
  const cell = page.getByTitle('Click to update preferences for Team on date 02');
  await expect(cell.getByRole('img', { name: 'Request description' })).toHaveCount(2);
  await cell.click();
  const editor = page.getByRole('dialog', { name: 'Shift Preference Matrix' });
  const dayDescription = editor.getByLabel('Request description for D');
  await expect(dayDescription).toHaveValue('Shared note');
  await dayDescription.fill('Appointment');
  await dayDescription.press('Enter');
  await dayDescription.pressSequentially('a');
  await expect(dayDescription).toHaveValue('Appointment\na');
  await editor.getByRole('button', { name: 'Save Preferences' }).click();

  const dayTwo = page.getByRole('article').filter({ hasText: 'Weight: +2', has: page.getByText('Date: 02', { exact: true }) });
  await expect(dayTwo).toContainText('Appointment');
  const shared = page.getByRole('article').filter({ hasText: 'Shared note' });
  await expect(shared).toContainText('Date: 01, 03');
  await expect(page.getByRole('article').filter({ hasText: 'Night note' })).toContainText('Weight: -1');

  await page.keyboard.press('Control+z');
  await expect(shared).toContainText('Date: 01, 02, 03');
  await expect(dayTwo).toHaveCount(0);
  await page.keyboard.press('Control+y');
  await expect(dayTwo).toBeVisible();

  await dayTwo.getByRole('button', { name: 'Edit description' }).click();
  await dayTwo.getByLabel('Request description for all listed dates').fill('Shared note');
  await dayTwo.getByRole('button', { name: 'Save description' }).click();
  await expect(shared).toContainText('Date: 01, 02, 03');

  await page.goto('/save-and-load');
  const preview = page.locator('pre');
  await expect(preview).toContainText('Shared note');
  expect(yaml.load(await preview.innerText())).toMatchObject({
    preferences: [
      { person: ['Team'], date: ['01', '02', '03'], shiftType: ['D'], weight: 2, description: 'Shared note' },
      { person: ['Team'], date: ['02'], shiftType: ['N'], weight: -1, description: 'Night note' },
    ],
  });
});

test('edits descriptions on imported selectors without combining overlapping requests', async ({ page }) => {
  await seedScheduleSpecState(page, {
    ...scheduleSpec,
    preferences: [
      { type: 'shift request', person: ['P1', 'P2'], date: ['01', '02'], shiftType: ['D', 'N'], weight: 1, description: 'Imported request' },
      { type: 'shift request', person: ['P1'], date: ['ALL'], shiftType: ['D'], weight: 2, description: 'All dates' },
      { type: 'shift request', person: ['P1'], date: ['WEEKEND'], shiftType: ['D'], weight: 2, description: 'Weekend dates' },
    ],
  });

  await page.goto('/shift-requests');
  const imported = page.getByRole('article').filter({ hasText: 'P1, P2' });
  await imported.getByRole('button', { name: 'Edit description' }).click();
  await imported.getByLabel('Request description for all listed dates').fill('Combined staffing request');
  await imported.getByRole('button', { name: 'Save description' }).click();

  const weekend = page.getByRole('article').filter({ hasText: 'Date: WEEKEND' });
  await weekend.getByRole('button', { name: 'Edit description' }).click();
  await weekend.getByLabel('Request description for all listed dates').fill('All dates');
  await weekend.getByRole('button', { name: 'Save description' }).click();
  await expect(page.getByRole('article').filter({ hasText: 'All dates' })).toHaveCount(2);

  await page.goto('/save-and-load');
  const preview = page.locator('pre');
  await expect(preview).toContainText('Combined staffing request');
  const { preferences } = yaml.load(await preview.innerText()) as { preferences: unknown[] };
  expect(preferences).toHaveLength(3);
  expect(preferences).toEqual(expect.arrayContaining([
    expect.objectContaining({ person: ['P1', 'P2'], date: ['01', '02'], shiftType: ['D', 'N'], weight: 1, description: 'Combined staffing request' }),
    expect.objectContaining({ person: ['P1'], date: ['ALL'], shiftType: ['D'], weight: 2, description: 'All dates' }),
    expect.objectContaining({ person: ['P1'], date: ['WEEKEND'], shiftType: ['D'], weight: 2, description: 'All dates' }),
  ]));
});

test('quick add preserves descriptions and separate weights on an already requested date', async ({ page }) => {
  await seedScheduleSpecState(page, {
    ...scheduleSpec,
    preferences: [
      { type: 'shift request', person: ['P1'], date: ['01', '02'], shiftType: ['D'], weight: 2, description: 'Shared note' },
      { type: 'shift request', person: ['P1'], date: ['02'], shiftType: ['D'], weight: 3, description: 'Second note' },
    ],
  });

  await page.goto('/shift-requests');
  await expect(page.getByRole('article').filter({ hasText: 'Shared note' })).toContainText('Date: 01, 02');
  await page.getByRole('button', { name: 'Quick Add Preference' }).click();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByPlaceholder('Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)').fill('3');
  await page.getByTitle('Click or drag to update preferences for P1 on date 02').click();

  const sameDate = page.getByRole('article').filter({ has: page.getByText('Date: 02', { exact: true }) });
  await expect(sameDate).toHaveCount(2);
  await expect(sameDate.filter({ hasText: 'Shared note' })).toContainText('Weight: +3');
  const secondRequest = sameDate.filter({ hasText: 'Second note' });
  await expect(secondRequest).toContainText('Weight: +3');
  await secondRequest.getByRole('button', { name: 'Edit description' }).click();
  await secondRequest.getByLabel('Request description for all listed dates').fill('Shared note');
  await sameDate.getByRole('button', { name: 'Save description' }).click();
  await expect(sameDate.filter({ hasText: 'Shared note' })).toHaveCount(2);

  await page.getByRole('heading', { name: 'Shift Requests', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(secondRequest).toBeVisible();
  await page.keyboard.press('Control+z');
  const shared = page.getByRole('article').filter({ hasText: 'Shared note' });
  await expect(shared).toContainText('Date: 01, 02');
  await expect(shared).toContainText('Weight: +2');
  await expect(sameDate).toHaveCount(1);
});
