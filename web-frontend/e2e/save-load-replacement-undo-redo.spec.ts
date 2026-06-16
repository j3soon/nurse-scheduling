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
import { seedSchedulingState, waitForStoredCurrentSchedulingData } from './helpers';

test('uploading replacement YAML is one undoable state boundary over the prior schedule', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed an original schedule and confirm its downstream entities are present.
   * 2. Upload a distinct YAML replacement through Save and Load.
   * 3. Confirm the replacement state fully overwrote the original state.
   * 4. Undo and redo the upload to verify the whole replacement is a single history step.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'original upload replacement seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Original nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Original shift' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  const replacementYaml = `apiVersion: test\ndescription: replacement upload state\ndates:\n  range:\n    startDate: 2026-06-01\n    endDate: 2026-06-01\n  groups: []\npeople:\n  items:\n    - id: P9\n      description: Replacement nurse\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: ZX\n      description: Replacement shift\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await page.goto('/shift-types');
  await expect(page.getByText('1. D', { exact: true })).toBeVisible();

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'replacement.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(replacementYaml, 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(2);
  await expect(page.locator('pre')).toContainText('replacement upload state');
  await waitForStoredCurrentSchedulingData(page, 'P9');

  await page.goto('/people');
  await expect(page.getByText('1. P9', { exact: true })).toBeVisible();
  await expect(page.getByText('P1', { exact: true })).toHaveCount(0);
  await page.goto('/shift-types');
  await expect(page.getByText('1. ZX', { exact: true })).toBeVisible();
  await expect(page.getByText('1. D', { exact: true })).toHaveCount(0);

  await page.getByRole('heading', { name: 'Shift Type Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('1. D', { exact: true })).toBeVisible();
  await waitForStoredCurrentSchedulingData(page, 'P1');

  await page.goto('/people');
  await expect(page.getByText('1. P1', { exact: true })).toBeVisible();
  await expect(page.getByText('P9', { exact: true })).toHaveCount(0);
  await page.goto('/shift-types');
  await expect(page.getByText('1. D', { exact: true })).toBeVisible();
  await expect(page.getByText('1. ZX', { exact: true })).toHaveCount(0);

  await page.getByRole('heading', { name: 'Shift Type Management', exact: true }).click();
  await page.keyboard.press('Control+y');
  await expect(page.getByText('1. ZX', { exact: true })).toBeVisible();
  await waitForStoredCurrentSchedulingData(page, 'P9');

  await page.goto('/people');
  await expect(page.getByText('1. P9', { exact: true })).toBeVisible();
  await expect(page.getByText('P1', { exact: true })).toHaveCount(0);
  await page.goto('/shift-types');
  await expect(page.getByText('1. ZX', { exact: true })).toBeVisible();
  await expect(page.getByText('1. D', { exact: true })).toHaveCount(0);
});
