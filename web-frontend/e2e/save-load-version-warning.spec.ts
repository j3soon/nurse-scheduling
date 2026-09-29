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
import { seedSchedulingState } from './helpers';

test('version warning appears after immediate upload and the upload can be undone', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed the original group and upload a file with a mismatched app version.
   * 2. Confirm the new group applies immediately and the warning appears inline.
   * 3. Undo the upload and confirm the original group returns.
   */
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'original seed',
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
      groups: [
        { id: 'Team Alpha', members: ['P1'], description: 'Original team' },
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
    ],
    export: {
      formatting: [],
    },
  });

  await page.goto('/save-and-load');
  await expect(page.getByRole('heading', { name: 'Save and Load' })).toBeVisible();
  await expect(page.locator('pre')).toContainText('Team Alpha');
  const currentYaml = await page.locator('pre').textContent();
  await page.goto('/people');
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Omega', { exact: true })).toHaveCount(0);
  await page.goto('/save-and-load');
  const yamlWithoutAppVersion = (currentYaml ?? '').replace(/^appVersion: .*$/m, '').trimStart();
  const mismatchedYaml = `appVersion: mismatch-version\n${yamlWithoutAppVersion}`.replace('Team Alpha', 'Team Omega');

  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.dismiss();
  });
  await page.locator('input[type="file"]').setInputFiles({
    name: 'mismatch.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(mismatchedYaml, 'utf8'),
  });
  const summary = page.getByRole('status', { name: 'YAML import summary' });
  await expect(summary).toContainText('Schedule uploaded: mismatch.yaml');
  await expect(summary).toContainText('App version mismatch detected');
  await expect(page.locator('pre')).toContainText('Team Omega');
  expect(dialogs).toHaveLength(0);

  await page.getByRole('heading', { name: 'Save and Load' }).click();
  await page.keyboard.press('Control+z');
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await expect(page.locator('pre')).not.toContainText('Team Omega');
  await page.goto('/people');
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Omega', { exact: true })).toHaveCount(0);
});
