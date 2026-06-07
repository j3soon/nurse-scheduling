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

test('export formatting rules affect the YAML sent to optimize and export', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal schedule and confirm there is no formatting rule yet.
   * 2. Add one export formatting rule through the real page UI.
   * 3. Trigger optimize with a mocked backend.
   * 4. Confirm the posted YAML contains the export formatting rule.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'formatting body seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await page.goto('/export-layout');
  await expect(page.getByText('No style rules defined yet. Click "Add Export Rule" to get started.')).toBeVisible();
  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.locator('select').nth(1).selectOption('cell');
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByTitle('Enter background color in hex').fill('#00ff00');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Background: #00ff00')).toBeVisible();
  await page.goto('/save-and-load');
  await expect(page.locator('pre')).toContainText('00ff00');

  let submittedBody = '';
  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  expect(submittedBody).toContain('formatting');
  expect(submittedBody).toContain('backgroundColor');
  expect(submittedBody).toContain('00ff00');
  expect(submittedBody).toContain('shiftTypes');
  expect(submittedBody).toContain('D');
});
