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
import { disableModalDialogs, seedMinimalScheduleSpecState } from './helpers';

test.describe('Traditional Chinese interface', () => {
  test.use({ locale: 'zh-TW' });

  test('detects the browser across all pages and preserves user content', async ({ page }) => {
    await disableModalDialogs(page);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await seedMinimalScheduleSpecState(page);
    for (const [path, heading] of [
      ['/', '護理人員排班系統'],
      ['/dates', '日期管理'],
      ['/people', '人員管理'],
      ['/shift-types', '班別管理'],
      ['/shift-type-requirements', '班別需求'],
      ['/shift-requests', '排班請求'],
      ['/shift-type-successions', '班別接續'],
      ['/shift-counts', '班次計數'],
      ['/shift-affinities', '同班偏好'],
      ['/export-layout', '匯出配置'],
      ['/save-and-load', '儲存與載入'],
      ['/optimize-and-export', '最佳化與匯出'],
      ['/experimental-ai', '排班 AI 對話'],
    ]) {
      await page.goto(path);
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', 'zh-TW');
    }
    await expect(page.getByRole('textbox', { name: '詢問目前的排班設定' })).toBeVisible();
    await page.goto('/people');
    await expect(page.getByTestId('data-table-people').getByText('1. Person 1', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '新增人員', exact: true }).click();
    await expect(page.getByRole('heading', { name: '新增人員', exact: true })).toBeVisible();
    await page.getByRole('button', { name: '新增', exact: true }).click();
    await expect(page.getByText('人員 ID 不得為空', { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('saved English overrides browser detection on reload', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('nurse-scheduling-language', 'en'));
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Nurse Scheduling System', exact: true })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await page.reload();
    await expect(page.getByRole('button', { name: 'New Schedule Spec', exact: true })).toBeVisible();
  });
});
