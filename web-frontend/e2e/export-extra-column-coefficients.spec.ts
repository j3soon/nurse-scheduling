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

test('extra column coefficients persist through Save and Load YAML and page navigation', async ({ page }) => {
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'coefficient persistence seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }, { id: 'N', description: 'Night' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [], extraColumns: [], extraRows: [] },
  });

  await page.goto('/export-layout');
  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.locator('select').first().selectOption('extra column');
  await page.getByPlaceholder('OFF (Weekend)').fill('Weighted shifts');
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByRole('checkbox', { name: 'N', exact: true }).check();
  await page.getByRole('spinbutton', { name: 'N' }).fill('3');
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await page.goto('/save-and-load');
  const yamlPreview = page.locator('pre');
  await expect(yamlPreview).toContainText('header: Weighted shifts');
  await expect(yamlPreview).toContainText('countShiftTypeCoefficients');
  await expect(yamlPreview).toContainText('[N, 3]');

  await page.goto('/export-layout');
  await page.reload();
  const extraColumnCard = page.getByText('Header: Weighted shifts').locator(
    'xpath=ancestor::div[contains(@class, "px-4 py-2")][1]'
  );
  await extraColumnCard.getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByRole('spinbutton', { name: 'D' })).toHaveValue('');
  await expect(page.getByRole('spinbutton', { name: 'N' })).toHaveValue('3');
});
