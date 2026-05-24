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
import yaml from 'js-yaml';

test('upload can replace the current renamed save-load preview with an older saved YAML', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed and capture YAML with the original person name.
   * 2. Rename that person through the People page.
   * 3. Upload the original YAML.
   * 4. Confirm the original name returns in the preview and the renamed preview is gone.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'replace renamed upload seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/save-and-load');
  const originalYaml = await page.locator('pre').textContent();
  await expect(page.locator('pre')).toContainText('P1');

  await page.goto('/people');
  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await peopleTable.locator('tr').filter({ has: page.getByText('1. P1', { exact: true }) }).getByRole('button', { name: 'Edit' }).click();
  await page.getByPlaceholder('Enter person ID').fill('P1X');
  await page.getByRole('button', { name: 'Update' }).click();
  await expect(page.getByText('1. P1X', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'original.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(originalYaml ?? '', 'utf8'),
  });
  await expect(page.locator('pre')).toContainText('P1');
  await expect(page.locator('pre')).not.toContainText('P1X');

  expect(yaml.load((await page.locator('pre').textContent()) ?? '')).toEqual(yaml.load(originalYaml ?? ''));
  await expect(page.locator('pre')).not.toContainText('P1X');
});
