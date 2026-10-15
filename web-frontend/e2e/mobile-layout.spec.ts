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
import yaml from 'js-yaml';
import { disableModalDialogs, mockOptimizeAndExport, seedSchedulingState } from './helpers';

const pages = [
  { route: '/', edit: null },
  { route: '/people', edit: 'Add Person' },
  { route: '/dates', edit: 'Set Date Range' },
  { route: '/shift-types', edit: 'Add Shift Type' },
  { route: '/shift-requests', edit: 'Quick Add Preference' },
  { route: '/shift-counts', edit: 'Add Shift Count' },
  { route: '/shift-type-requirements', edit: 'Add Requirement' },
  { route: '/shift-affinities', edit: 'Add Shift Affinity' },
  { route: '/shift-type-successions', edit: 'Add Succession' },
  { route: '/export-layout', edit: 'Add Export Rule' },
  { route: '/optimize-and-export', edit: null },
  { route: '/save-and-load', edit: 'Edit YAML' },
];

test.describe.configure({ mode: 'parallel' });

test.use({ hasTouch: true, isMobile: true, viewport: { width: 360, height: 740 } });

test.beforeEach(async ({ page }) => {
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test', description: 'Phone editing schedule',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-31' }, groups: [] },
    people: { items: [
      { id: 'Alice', description: 'Day team', history: [] },
      { id: 'Bob', description: 'Night team', history: [] },
    ], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }, { id: 'N', description: 'Night' }], groups: [] },
    preferences: [
      { type: 'at most one shift per day' },
      { type: 'shift count', person: ['Alice'], countDates: ['01'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2, description: 'Day count' },
      { type: 'shift count', person: ['Bob'], countDates: ['02'], countShiftTypes: ['N'], expression: 'x <= T', target: 3, weight: 1, description: 'Night count' },
      { type: 'shift type requirement', shiftType: ['D'], requiredNumPeople: 1, qualifiedPeople: ['Alice'], date: ['01'], weight: -1, description: 'Day coverage' },
      { type: 'shift type successions', person: ['Alice'], pattern: ['N', 'D'], date: ['01'], weight: -1, description: 'Night to day' },
      { type: 'shift affinity', date: ['01'], people1: ['Alice'], people2: ['Bob'], shiftTypes: ['D'], weight: 1, description: 'Day pair' },
    ],
    export: { formatting: [{ type: 'cell', targets: ['D'], backgroundColor: '#00ff00' }], extraColumns: [], extraRows: [] },
  });
  await mockOptimizeAndExport(page);
});

for (const { route, edit } of pages) {
  test(`keeps ${route} and its editing controls within the phone screen`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator('h1')).toBeVisible();
    // The saved custom layout indicator confirms that the seeded schedule has loaded.
    await expect(page.getByTestId('custom-export-layout-indicator')).toBeAttached();
    for (const width of [360, 390, 844]) {
      await page.setViewportSize({ width, height: width === 844 ? 390 : 844 });
      expect.soft(await page.evaluate(() => document.documentElement.scrollWidth), `${route} at ${width}px`).toBeLessThanOrEqual(width);
    }
    if (edit) {
      await page.getByRole('button', { name: edit, exact: true }).tap();
      for (const width of [360, 390, 844]) {
        await page.setViewportSize({ width, height: width === 844 ? 390 : 844 });
        expect.soft(await page.evaluate(() => document.documentElement.scrollWidth), `${route} editor at ${width}px`).toBeLessThanOrEqual(width);
      }
    }
  });
}


test('edits and reorders people by touch and retains the changes after reload', async ({ page }) => {
  await page.goto('/people');
  const alice = page.getByText('1. Alice', { exact: true });
  await expect(alice).toBeVisible();
  await alice.tap();
  const input = page.locator('input[value="Alice"]');
  await expect(input).toBeVisible();
  await expect(input).toHaveCSS('font-size', '16px');
  await input.fill('Alicia');
  await input.press('Tab');
  await expect(page.getByText('1. Alicia', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move People row 2 up', exact: true }).tap();
  await expect(page.getByText('1. Bob', { exact: true })).toBeVisible();
  await expect(page.getByText('2. Alicia', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('2. Alicia', { exact: true })).toBeVisible();
});

test('selects and saves a date range with taps', async ({ page }) => {
  await page.goto('/dates');
  await expect(page.getByText('Duration: 31 days')).toBeVisible();
  await page.getByRole('button', { name: 'Set Date Range', exact: true }).tap();
  await page.getByRole('button', { name: 'Select 2026-05-03', exact: true }).tap();
  await page.getByRole('button', { name: 'Select 2026-05-05', exact: true }).tap();
  await expect(page.locator('#startDate')).toHaveValue('2026-05-03');
  await expect(page.locator('#endDate')).toHaveValue('2026-05-05');
  await page.getByRole('button', { name: /Apply|Update/ }).tap();
  await expect(page.getByText('Duration: 3 days')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Duration: 3 days')).toBeVisible();
});

test('reorders preference cards and edits the saved YAML on a phone', async ({ page }) => {
  await page.goto('/shift-counts');
  await expect(page.getByText('Day count', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move Current Shift Counts item 2 up', exact: true }).tap();
  await page.goto('/save-and-load');
  await page.getByRole('button', { name: 'Edit YAML', exact: true }).tap();
  const input = page.getByPlaceholder('Enter YAML configuration...');
  const original = await input.inputValue();
  expect(original.indexOf('Night count')).toBeLessThan(original.indexOf('Day count'));
  await input.fill(original.replace('Phone editing schedule', 'Edited from phone'));
  await page.getByRole('button', { name: 'Save', exact: true }).tap();
  await page.reload();
  await expect(page.getByText('Edited from phone', { exact: false })).toBeVisible();
});

test('reorders a succession pattern without dragging', async ({ page }) => {
  await page.goto('/shift-type-successions');
  await expect(page.getByText('Night to day', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit', exact: true }).tap();
  await page.getByRole('button', { name: 'Move D at position 2 left', exact: true }).tap();
  await page.getByRole('button', { name: 'Update', exact: true }).tap();
  await page.goto('/save-and-load');
  await page.getByRole('button', { name: 'Edit YAML', exact: true }).tap();
  const saved = yaml.load(await page.getByPlaceholder('Enter YAML configuration...').inputValue()) as { preferences: { type: string; pattern?: string[] }[] };
  expect(saved.preferences.find(preference => preference.type === 'shift type successions')?.pattern).toEqual(['D', 'N']);
});

test('fits the home page title and actions to a phone', async ({ page }) => {
  await page.goto('/');
  const title = page.getByRole('heading', { name: 'Nurse Scheduling System', level: 1 });
  // One line of text, starting near the top instead of the vertical center.
  const titleBox = (await title.boundingBox())!;
  expect(titleBox.height).toBeLessThan(40);
  expect(titleBox.y).toBeLessThan(250);
  const newSchedule = (await page.getByRole('button', { name: 'New Schedule', exact: true }).boundingBox())!;
  const menu = (await page.getByRole('button', { name: 'Choose new schedule type' }).boundingBox())!;
  const continueBox = (await page.getByRole('button', { name: 'Continue', exact: true }).boundingBox())!;
  expect(Math.abs(newSchedule.width + menu.width - continueBox.width)).toBeLessThanOrEqual(2);
  // The build selector follows the actions instead of floating over them.
  const build = (await page.getByRole('button', { name: /^Build:/ }).boundingBox())!;
  expect(build.y).toBeGreaterThan(continueBox.y + continueBox.height);
});

test('keeps backend server names readable in the phone backend table', async ({ page }) => {
  await page.goto('/optimize-and-export');
  const header = page.getByRole('columnheader', { name: 'Server', exact: true });
  await expect(header).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Activity', exact: true })).toBeHidden();
  expect((await header.boundingBox())!.width).toBeGreaterThan(100);
  const serverName = page.getByTestId('data-table-backend').getByText('http://localhost:8000', { exact: true });
  await serverName.tap();
  await expect(page.getByRole('radio', { name: 'Select http://localhost:8000' })).toBeChecked();
  await expect(page.locator('input[type="text"]:focus')).toHaveCount(0);
  await serverName.tap();
  await expect(page.locator('input[type="text"]:focus')).toHaveValue('http://localhost:8000');
});

test('shows whole date lists, a collapsed copy panel, and a centered current tab on a phone', async ({ page }) => {
  await page.goto('/shift-type-requirements');
  const currentTab = page.getByRole('button', { name: '4. Shift Type Requirements', exact: true });
  await expect(currentTab).toHaveAttribute('aria-current', 'page');
  await expect.poll(async () => {
    const box = (await currentTab.boundingBox())!;
    return Math.abs(box.x + box.width / 2 - 180);
  }).toBeLessThanOrEqual(2);
  // Rotating the phone keeps the current tab centered.
  await page.setViewportSize({ width: 740, height: 360 });
  await expect.poll(async () => {
    const box = (await currentTab.boundingBox())!;
    return Math.abs(box.x + box.width / 2 - 370);
  }).toBeLessThanOrEqual(2);
  await page.setViewportSize({ width: 360, height: 740 });
  // A height-only resize, as when a phone toolbar collapses, keeps the user's swipe.
  await expect.poll(async () => {
    const box = (await currentTab.boundingBox())!;
    return Math.abs(box.x + box.width / 2 - 180);
  }).toBeLessThanOrEqual(2);
  await currentTab.evaluate(tab => { tab.closest('.overflow-x-auto')!.scrollLeft = 0; });
  await page.setViewportSize({ width: 360, height: 680 });
  await page.waitForTimeout(200);
  expect(await currentTab.evaluate(tab => tab.closest('.overflow-x-auto')!.scrollLeft)).toBe(0);
  await page.setViewportSize({ width: 360, height: 740 });
  await page.getByRole('button', { name: 'Add Requirement', exact: true }).tap();
  const lastDate = page.locator('label').filter({ has: page.locator('input[type="checkbox"]') }).filter({ hasText: /^31$/ });
  // The list has no scroll box of its own, so its last row is not clipped.
  expect(await lastDate.evaluate(label => {
    for (let node = label.parentElement; node; node = node.parentElement) {
      if (node.scrollHeight > node.clientHeight + 1 && getComputedStyle(node).overflowY !== 'visible') return node.tagName;
    }
    return null;
  })).toBeNull();
  await page.goto('/people');
  await page.getByRole('button', { name: 'Add Person', exact: true }).tap();
  await expect(page.getByText('Apply selection from another person', { exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Source person' })).toBeHidden();
});
