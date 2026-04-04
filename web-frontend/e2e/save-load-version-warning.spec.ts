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

test('version warning upload respects cancel and continue branches', async ({ page }) => {
  /*
   * Steps:
   * 1. Confirm the original save/load YAML and people page still show the old group ID.
   * 2. Upload a mismatched-version YAML and cancel the warning; confirm state stays unchanged.
   * 3. Upload the same YAML again and accept the warning.
   * 4. Confirm the renamed group is then applied.
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

  const cancelDialogPromise = page.waitForEvent('dialog');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'mismatch.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(mismatchedYaml, 'utf8'),
  });
  const cancelDialog = await cancelDialogPromise;
  expect(cancelDialog.message()).toContain('App version mismatch detected');
  await cancelDialog.dismiss();

  await page.goto('/people');
  await expect(page.getByTitle('Team Alpha', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Omega', { exact: true })).toHaveCount(0);

  await page.goto('/save-and-load');
  const proceedDialogPromise = page.waitForEvent('dialog');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'mismatch-confirmed.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(mismatchedYaml, 'utf8'),
  });
  const proceedDialog = await proceedDialogPromise;
  expect(proceedDialog.message()).toContain('App version mismatch detected');
  const successDialogPromise = page.waitForEvent('dialog');
  await proceedDialog.accept();
  const successDialog = await successDialogPromise;
  expect(successDialog.message()).toContain('YAML file loaded successfully');
  await successDialog.accept();
  await expect(page.locator('pre')).toContainText('Team Omega');

  await page.goto('/people');
  await expect(page.getByTitle('Team Omega', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Team Alpha', { exact: true })).toHaveCount(0);
});
