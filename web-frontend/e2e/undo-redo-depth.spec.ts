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

test('multi-step undo and redo preserve history after loading an invalid index', async ({ page }) => {
  await disableModalDialogs(page);

  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule Spec', exact: true }).click();
  await page.getByRole('button', { name: 'Create empty Schedule Spec' }).click();

  await page.goto('/people');
  await expect(page.getByRole('heading', { name: 'People Management', exact: true })).toBeVisible();
  await expect(page.getByText('Night Owl', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Early Bird', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Add Person' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Night Owl');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Night Owl', { exact: true })).toBeVisible();
  await expect(page.getByText('Early Bird', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Add Person' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Early Bird');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Night Owl', { exact: true })).toBeVisible();
  await expect(page.getByText('Early Bird', { exact: true })).toBeVisible();

  await page.evaluate(() => {
    const namespace = window.__PLAYWRIGHT_WORKER_NAMESPACE__;
    const key = namespace ? `nurse-scheduling-spec__${namespace}` : 'nurse-scheduling-spec';
    const saved = JSON.parse(localStorage.getItem(key)!);
    localStorage.setItem(key, JSON.stringify({ ...saved, currentHistoryIndex: 'invalid' }));
  });
  await page.reload();
  await expect(page.getByText('Early Bird', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add Person' }).click();
  await page.getByPlaceholder('Enter person ID').fill('Weekend Nurse');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Weekend Nurse', { exact: true })).toBeVisible();

  const undo = page.getByRole('button', { name: 'Undo', exact: true });
  await expect(undo).toBeEnabled();
  await undo.click();
  await expect(page.getByText('Weekend Nurse', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Early Bird', { exact: true })).toBeVisible();

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('Night Owl', { exact: true })).toBeVisible();
  await expect(page.getByText('Early Bird', { exact: true })).toHaveCount(0);

  await page.keyboard.press('Control+z');
  await expect(page.getByText('Night Owl', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Early Bird', { exact: true })).toHaveCount(0);

  await page.keyboard.press('Control+y');
  await expect(page.getByText('Night Owl', { exact: true })).toBeVisible();
  await expect(page.getByText('Early Bird', { exact: true })).toHaveCount(0);

  await page.keyboard.press('Control+y');
  await expect(page.getByText('Night Owl', { exact: true })).toBeVisible();
  await expect(page.getByText('Early Bird', { exact: true })).toBeVisible();
});
