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
import { disableModalDialogs } from './helpers';

// Backend inputs omit `description` and `history`, as every core testcase does.
const BACKEND_SHAPED_YAML = `apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-06
people:
  items:
    - id: n1
    - id: n2
  groups:
    - id: Team A
      members: [n1]
shiftTypes:
  items:
    - id: D
    - id: A
preferences:
  - type: at most one shift per day
`;

test('uploading backend-shaped YAML renders entity and shift-request pages', async ({ page }) => {
  /*
   * Steps:
   * 1. Upload a YAML file that omits every optional description and history.
   * 2. Confirm the people page renders its inline-editable descriptions.
   * 3. Confirm the shift requests page renders its history columns.
   */
  await disableModalDialogs(page);
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
  });
  const pageErrors: string[] = [];
  page.on('pageerror', error => {
    pageErrors.push(error.message);
  });

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'backend-shaped.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(BACKEND_SHAPED_YAML, 'utf8'),
  });
  await expect.poll(() => dialogs.some(message => message.includes('YAML file loaded successfully!'))).toBe(true);

  await page.goto('/people');
  await expect(page.getByRole('row', { name: /1\. n1/ })).toBeVisible();
  await expect(page.getByRole('row', { name: /^Team A/ })).toBeVisible();
  // The placeholder proves the omitted description reached InlineEdit as a string.
  await expect(page.getByText('Add description...').first()).toBeVisible();

  await page.goto('/shift-requests');
  await expect(page.getByRole('row', { name: /1\. n1/ })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'H-1' })).toBeVisible();

  expect(pageErrors).toEqual([]);
});
