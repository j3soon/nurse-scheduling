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
import { disableModalDialogs, seedSchedulingState, waitForStoredCurrentSchedulingData } from './helpers';

test('save and load roundtrip restores seeded state after reset', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the seeded state exists before any reset.
   * 2. Reset the app from the home-page flow and verify the original state disappears.
   * 3. Upload the saved YAML back through save/load.
   * 4. Confirm the original people and preference data return.
   */
  await disableModalDialogs(page);
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
  });
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'roundtrip seed',
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
      ],
      groups: [],
    },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 3, description: 'request' },
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/save-and-load');
  await expect(page.getByRole('heading', { name: 'Save and Load' })).toBeVisible();
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await expect(page.locator('pre')).toContainText('shift request');
  const yamlText = await page.locator('pre').textContent();
  expect(yamlText).toContain('Team Alpha');
  expect(yamlText).toContain('shift request');

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule' }).click();
  await page.getByRole('button', { name: 'Reset Data' }).click();

  await page.goto('/people');
  await expect(page.getByText('Team Alpha')).toHaveCount(0);

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'roundtrip.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await expect.poll(() => dialogs.some(message => message.includes('YAML file loaded successfully!'))).toBe(true);
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await waitForStoredCurrentSchedulingData(page, 'Team Alpha');

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByText('Person: P1')).toBeVisible();
  await expect(page.getByText('Shift Type: D')).toBeVisible();
});
