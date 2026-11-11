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
      ['/export-layout', '匯出版面'],
      ['/save-and-load', '儲存與載入'],
      ['/optimize-and-export', '最佳化與匯出'],
      ['/experimental-ai', '排班 AI 對話'],
    ]) {
      await page.goto(path);
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', 'zh-TW');
      await expect(page).toHaveTitle('護理人員排班系統');
      await expect(page.locator('head title')).toHaveCount(1);
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
    await expect(page).toHaveTitle('Nurse Scheduling System');
    await page.reload();
    await expect(page.getByRole('button', { name: 'New Schedule Spec', exact: true })).toBeVisible();
  });
});

test.describe('manual language selection', () => {
  test.use({ locale: 'en-US' });

  test('remembers the choice without changing Schedule Spec data or Undo/Redo history', async ({ page }) => {
    await disableModalDialogs(page);
    await seedMinimalScheduleSpecState(page);
    await page.goto('/people');
    await expect(page.getByTestId('data-table-people').getByTitle('1. Person 1', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Add Person', exact: true }).click();
    await page.getByPlaceholder('Enter person ID', { exact: true }).fill('Nurse Kept');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(page.getByTestId('data-table-people').getByTitle('2. Nurse Kept', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '0. Home', exact: true }).click();
    const snapshot = () => page.evaluate(() => Object.fromEntries(
      Object.keys(localStorage).filter(key => key.startsWith('nurse-scheduling-spec'))
        .map(key => [key, localStorage.getItem(key)]),
    ));
    const before = await snapshot();
    await page.getByRole('combobox', { name: 'Language', exact: true }).selectOption('zh-TW');
    await expect(page.getByRole('heading', { name: '護理人員排班系統', exact: true })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-TW');
    await expect(page).toHaveTitle('護理人員排班系統');
    await expect(page.locator('head title')).toHaveCount(1);
    await expect(page).toHaveURL(/\/$/);
    expect(await snapshot()).toEqual(before);
    await page.reload();
    await expect(page.getByRole('combobox', { name: '語言', exact: true })).toHaveValue('zh-TW');
    await page.getByRole('button', { name: '2. 人員', exact: true }).click();
    const people = page.getByTestId('data-table-people');
    await expect(people.getByTitle('2. Nurse Kept', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '復原', exact: true }).click();
    await expect(people.getByTitle('2. Nurse Kept', { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: '重做', exact: true }).click();
    await expect(people.getByTitle('2. Nurse Kept', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '0. 首頁', exact: true }).click();
    await page.getByRole('combobox', { name: '語言', exact: true }).selectOption('en');
    await page.reload();
    await expect(page.getByRole('combobox', { name: 'Language', exact: true })).toHaveValue('en');
    await expect(page).toHaveTitle('Nurse Scheduling System');
  });
});

test.describe('language selection on a phone', () => {
  test.use({ locale: 'en-US', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('keeps the selector and populated editing forms within the viewport', async ({ page }) => {
    await disableModalDialogs(page);
    await seedMinimalScheduleSpecState(page);
    await page.reload();
    await page.getByRole('combobox', { name: 'Language', exact: true }).selectOption('zh-TW');
    const selector = page.getByRole('combobox', { name: '語言', exact: true });
    await expect(selector).toHaveValue('zh-TW');
    const bounds = await selector.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
    await page.getByRole('button', { name: '2. 人員', exact: true }).tap();
    await expect(page.getByTestId('data-table-people').getByTitle('1. Person 1', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '新增人員', exact: true }).tap();
    await expect(page.getByRole('heading', { name: '新增人員', exact: true })).toBeVisible();
    await page.getByPlaceholder('輸入人員 ID', { exact: true }).fill('Touch draft');
    const globe = page.getByRole('navigation').getByRole('combobox', { name: '切換語言', exact: true });
    const globeBounds = await globe.boundingBox();
    expect(globeBounds!.width).toBeGreaterThanOrEqual(44);
    expect(globeBounds!.height).toBeGreaterThanOrEqual(44);
    expect(globeBounds!.x + globeBounds!.width).toBeLessThanOrEqual(390);
    await globe.tap();
    await globe.selectOption('en');
    await page.keyboard.press('Escape');
    await expect(page.getByPlaceholder('Enter person ID', { exact: true })).toHaveValue('Touch draft');
    const size = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
    expect(size.width).toBeLessThanOrEqual(size.viewport);
  });
});

test('the navigation globe switches language with the keyboard and preserves unsaved edits', async ({ page }) => {
  await disableModalDialogs(page);
  await seedMinimalScheduleSpecState(page);
  await page.goto('/people');
  await page.getByRole('button', { name: 'Add Person', exact: true }).click();
  await page.getByPlaceholder('Enter person ID', { exact: true }).fill('Draft nurse');
  await page.getByPlaceholder('Enter person description (optional)', { exact: true }).fill('Draft ward');
  const language = page.getByRole('navigation').getByRole('combobox', { name: 'Change language', exact: true });
  const redo = await page.getByRole('button', { name: 'Redo', exact: true }).boundingBox();
  const bounds = await language.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(redo!.x + redo!.width);
  await language.focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Escape');
  const chinese = page.getByRole('navigation').getByRole('combobox', { name: '切換語言', exact: true });
  await expect(chinese).toHaveValue('zh-TW');
  await expect(chinese).toBeFocused();
  await expect(page).toHaveURL(/\/people$/);
  await expect(page.getByPlaceholder('輸入人員 ID', { exact: true })).toHaveValue('Draft nurse');
  await expect(page.getByPlaceholder('輸入人員的說明（選填）', { exact: true })).toHaveValue('Draft ward');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await page.getByRole('button', { name: '0. 首頁', exact: true }).click();
  await expect(page.getByRole('main').getByRole('combobox', { name: '語言', exact: true })).toHaveValue('zh-TW');
  await page.getByRole('main').getByRole('combobox', { name: '語言', exact: true }).selectOption('en');
  await expect(page.getByRole('navigation').getByRole('combobox', { name: 'Change language', exact: true })).toHaveValue('en');
  await page.getByRole('navigation').getByRole('combobox', { name: 'Change language', exact: true }).selectOption('zh-TW');
  await page.reload();
  await expect(page.getByRole('navigation').getByRole('combobox', { name: '切換語言', exact: true })).toHaveValue('zh-TW');
});
