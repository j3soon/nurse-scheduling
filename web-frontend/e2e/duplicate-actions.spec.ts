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
import type { Page } from '@playwright/test';
import { disableModalDialogs, waitForStoredCurrentSchedulingData } from './helpers';

const STORAGE_KEY = 'nurse-scheduling-data';
const WORKER_NAMESPACE_KEY = '__PLAYWRIGHT_WORKER_NAMESPACE__';

const baseState = {
  apiVersion: 'v2',
  description: '',
  dates: {
    range: {
      startDate: '2026-05-01',
      endDate: '2026-05-01',
    },
    items: [],
    groups: [],
  },
  people: {
    items: [
      { id: 'Alice', description: 'Charge nurse', history: ['ICU'] },
      { id: 'Bob', description: 'Float nurse', history: [] },
    ],
    groups: [
      { id: 'Team A', members: ['Alice', 'Bob'], description: 'Primary team' },
    ],
    history: [],
  },
  shiftTypes: {
    items: [
      { id: 'D', description: 'Day' },
      { id: 'N', description: 'Night' },
    ],
    groups: [],
  },
  preferences: [
    {
      type: 'at most one shift per day',
    },
  ],
  export: {
    formatting: [
      {
        description: 'Style day cells',
        type: 'cell',
        people: ['Alice'],
        dates: ['01'],
        shiftTypes: ['D'],
        backgroundColor: '#fef3c7',
      },
    ],
    extraColumns: [
      {
        description: '',
        type: 'count',
        header: 'Day Count',
        countShiftTypes: ['D'],
        countDates: ['01'],
      },
    ],
    extraRows: [
      {
        description: '',
        type: 'count',
        header: 'Alice Count',
        countShiftTypes: ['D'],
        countPeople: ['Alice'],
      },
    ],
  },
};

async function seedStateBeforeNavigation(page: Page, state: Record<string, unknown>) {
  const persisted = JSON.stringify({
    state,
    history: [state],
    currentHistoryIndex: 0,
  });

  await page.addInitScript(
    ({ key, value, workerNamespaceKey }) => {
      const workerNamespace = (window as unknown as { [key: string]: string | undefined })[workerNamespaceKey];
      const storageKey = workerNamespace ? `${key}__${workerNamespace}` : key;
      window.localStorage.setItem(storageKey, value);
      window.localStorage.setItem(key, value);
      for (let workerIndex = 0; workerIndex < 8; workerIndex += 1) {
        window.localStorage.setItem(`${key}__worker-${workerIndex}`, value);
      }
    },
    { key: STORAGE_KEY, value: persisted, workerNamespaceKey: WORKER_NAMESPACE_KEY }
  );
}

async function seedDuplicateState(page: Page) {
  await seedStateBeforeNavigation(page, baseState);
}

async function openAddForm(page: Page, buttonName: string, headingName: string) {
  const heading = page.getByRole('heading', { name: headingName, exact: true });
  const button = page.getByRole('button', { name: buttonName, exact: true });

  await expect(async () => {
    if (await heading.count() === 0) {
      await button.click();
    }
    await expect(heading).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 10000 });
}

async function expectAddFormDismissed(page: Page, placeholder: string, draftText: string) {
  await expect(page.getByPlaceholder(placeholder)).toHaveCount(0);
  await expect.poll(async () =>
    page.locator('input, textarea').evaluateAll((fields, expectedValue) =>
      fields.filter((field) =>
        (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) &&
        field.value === expectedValue
      ).length,
    draftText)
  ).toBe(0);
}

test('item and group duplicate actions insert copies under the original without opening the editor', async ({ page }) => {
  await disableModalDialogs(page);
  await seedDuplicateState(page);
  await page.goto('/people');

  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const groupsTable = page.getByRole('heading', { name: 'People Groups', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');

  await peopleTable.locator('tr').filter({ has: page.getByText('1. Alice', { exact: true }) }).getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Alice copy');
  await expect(page.getByPlaceholder('Enter person ID')).toHaveCount(0);
  await expect(peopleTable.locator('tbody tr').nth(0)).toContainText('1. Alice');
  await expect(peopleTable.locator('tbody tr').nth(1)).toContainText('2. Alice copy');
  await expect(peopleTable.locator('tbody tr').nth(1)).toContainText('Charge nurse');
  await expect(peopleTable.locator('tbody tr').nth(1)).toContainText('Team A');
  await expect(peopleTable.locator('tbody tr').nth(2)).toContainText('3. Bob');

  await peopleTable.locator('tr').filter({ has: page.getByText('1. Alice', { exact: true }) }).getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Alice copy 2');
  await expect(peopleTable.locator('tbody tr').nth(1)).toContainText('2. Alice copy 2');
  await expect(peopleTable.locator('tbody tr').nth(2)).toContainText('3. Alice copy');

  await groupsTable.locator('tr').filter({ has: page.getByText('Team A', { exact: true }) }).getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Team A copy');
  await expect(page.getByPlaceholder('Enter group ID')).toHaveCount(0);
  await expect(groupsTable.locator('tbody tr').nth(0)).toContainText('Team A');
  await expect(groupsTable.locator('tbody tr').nth(1)).toContainText('Team A copy');
  await expect(groupsTable.locator('tbody tr').nth(1)).toContainText('Alice');
  await expect(groupsTable.locator('tbody tr').nth(1)).toContainText('Bob');

  await page.getByRole('heading', { name: 'People Management', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(groupsTable.getByText('Team A copy', { exact: true })).toHaveCount(0);

  await page.keyboard.press('Control+z');
  await expect(peopleTable.getByText('Alice copy 2', { exact: true })).toHaveCount(0);

  await page.keyboard.press('Control+y');
  await expect(peopleTable.locator('tbody tr').nth(1)).toContainText('2. Alice copy 2');
});

test('preference duplicate actions insert copied cards for each preference page', async ({ page }) => {
  await disableModalDialogs(page);
  await seedDuplicateState(page);

  await page.goto('/shift-counts');
  await openAddForm(page, 'Add Shift Count', 'Add New Shift Count');
  await page.getByPlaceholder('e.g., Working shifts should be close to the average').fill('count rule');
  await page.getByRole('checkbox', { name: 'Alice', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByPlaceholder('e.g., 5').fill('1');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'count rule copy');
  await expect(page.getByText('count rule', { exact: true })).toBeVisible();
  await expect(page.getByText('count rule copy', { exact: true })).toBeVisible();
  await expect(page.getByText('x >= 1', { exact: true })).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Add New Shift Count', exact: true })).toHaveCount(0);

  await page.goto('/shift-type-requirements');
  await openAddForm(page, 'Add Requirement', 'Add New Requirement');
  await page.getByPlaceholder('e.g., Night shifts need senior nurses').fill('requirement rule');
  await page.getByRole('radio', { name: 'D', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Alice', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'requirement rule copy');
  await expect(page.getByText('requirement rule', { exact: true })).toBeVisible();
  await expect(page.getByText('requirement rule copy', { exact: true })).toBeVisible();
  await expect(page.getByText(/Required:\s*1/)).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Add New Requirement', exact: true })).toHaveCount(0);

  await page.goto('/shift-type-successions');
  await openAddForm(page, 'Add Succession', 'Add New Succession');
  await page.getByPlaceholder('e.g., Forbid Evening -> Day succession').fill('succession rule');
  await page.getByRole('checkbox', { name: 'Alice', exact: true }).check();
  await page.getByRole('button', { name: 'N', exact: true }).click();
  await page.getByRole('button', { name: 'D', exact: true }).click();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'succession rule copy');
  await expect(page.getByText('succession rule', { exact: true })).toBeVisible();
  await expect(page.getByText('succession rule copy', { exact: true })).toBeVisible();
  await expect(page.getByText('Weight: -1')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Add New Succession', exact: true })).toHaveCount(0);

  await page.goto('/shift-affinities');
  await openAddForm(page, 'Add Shift Affinity', 'Add New Shift Affinity');
  await page.getByPlaceholder('e.g., Encourage newcomers and seniors to work together').fill('affinity rule');
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Alice', exact: true }).nth(0).check();
  await page.getByRole('checkbox', { name: 'Bob', exact: true }).nth(1).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'affinity rule copy');
  await expect(page.getByText('affinity rule', { exact: true })).toBeVisible();
  await expect(page.getByText('affinity rule copy', { exact: true })).toBeVisible();
  await expect(page.getByText('People 2: Bob')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Add New Shift Affinity', exact: true })).toHaveCount(0);
});

test('export layout duplicate actions insert copied entries for every export list', async ({ page }) => {
  await disableModalDialogs(page);
  await seedDuplicateState(page);
  await page.goto('/export-layout');

  const styleRules = page.getByRole('heading', { name: 'Style Rules', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const extraColumns = page.getByRole('heading', { name: 'Extra Columns', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  const extraRows = page.getByRole('heading', { name: 'Extra Rows', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');

  await styleRules.getByRole('button', { name: 'Duplicate' }).first().click();
  await waitForStoredCurrentSchedulingData(page, 'Style day cells copy');
  await expect(styleRules.getByText('Style day cells', { exact: true })).toBeVisible();
  await expect(styleRules.getByText('Style day cells copy', { exact: true })).toBeVisible();

  await extraColumns.getByRole('button', { name: 'Duplicate' }).first().click();
  await waitForStoredCurrentSchedulingData(page, 'Day Count');
  await expect(extraColumns.getByText('Copy', { exact: true })).toBeVisible();
  await expect(extraColumns.getByText('Header: Day Count')).toHaveCount(2);

  await extraRows.getByRole('button', { name: 'Duplicate' }).first().click();
  await waitForStoredCurrentSchedulingData(page, 'Alice Count');
  await expect(extraRows.getByText('Copy', { exact: true })).toBeVisible();
  await expect(extraRows.getByText('Header: Alice Count')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Add Export Rule', exact: true })).toHaveCount(0);
});

test('item group mutations dismiss open add drafts before mutating', async ({ page }) => {
  await disableModalDialogs(page);
  await seedDuplicateState(page);
  await page.goto('/people');

  const peopleTable = page.getByRole('heading', { name: 'People', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');

  await openAddForm(page, 'Add Person', 'Add New Person');
  await page.getByPlaceholder('Enter person ID').fill('Unsaved duplicate draft');
  await peopleTable.locator('tr').filter({ has: page.getByText('1. Alice', { exact: true }) }).getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Alice copy');
  await expectAddFormDismissed(page, 'Enter person ID', 'Unsaved duplicate draft');
  await expect(peopleTable.locator('tbody tr').nth(1)).toContainText('2. Alice copy');

  await openAddForm(page, 'Add Person', 'Add New Person');
  await page.getByPlaceholder('Enter person ID').fill('Unsaved delete draft');
  await peopleTable.locator('tr').filter({ has: page.getByText('3. Bob', { exact: true }) }).getByRole('button', { name: 'Delete' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Alice copy');
  await expectAddFormDismissed(page, 'Enter person ID', 'Unsaved delete draft');
  await expect(peopleTable.getByText('Bob', { exact: true })).toHaveCount(0);

  await openAddForm(page, 'Add Person', 'Add New Person');
  await page.getByPlaceholder('Enter person ID').fill('Unsaved tag draft');
  await peopleTable.getByTitle('Remove "Team A"').first().click();
  await waitForStoredCurrentSchedulingData(page, 'Alice copy');
  await expectAddFormDismissed(page, 'Enter person ID', 'Unsaved tag draft');
  await expect(peopleTable.locator('tbody tr').nth(0)).not.toContainText('Team A');

  await openAddForm(page, 'Add Person', 'Add New Person');
  await page.getByPlaceholder('Enter person ID').fill('Unsaved reorder draft');
  const rows = peopleTable.locator('tbody tr');
  await rows.nth(1).dragTo(rows.nth(0));
  await expectAddFormDismissed(page, 'Enter person ID', 'Unsaved reorder draft');
  await expect(rows.nth(0)).toContainText('1. Alice copy');
  await expect(rows.nth(1)).toContainText('2. Alice');
});

test('preference and export duplicate actions dismiss open add drafts before mutating', async ({ page }) => {
  await disableModalDialogs(page);
  await seedStateBeforeNavigation(page, {
    ...baseState,
    preferences: [
      { type: 'at most one shift per day' },
      {
        type: 'shift count',
        description: 'Existing count',
        person: ['Alice'],
        countDates: ['01'],
        countShiftTypes: ['D'],
        expression: 'x >= T',
        target: 1,
        weight: -1,
      },
      {
        type: 'shift type requirement',
        description: 'Existing requirement',
        shiftType: ['D'],
        requiredNumPeople: 1,
        qualifiedPeople: ['Alice'],
        date: ['01'],
        weight: -1,
      },
      {
        type: 'shift type successions',
        description: 'Existing succession',
        person: ['Alice'],
        pattern: ['N', 'D'],
        date: ['01'],
        weight: -1,
      },
      {
        type: 'shift affinity',
        description: 'Existing affinity',
        date: ['01'],
        people1: ['Alice'],
        people2: ['Bob'],
        shiftTypes: ['D'],
        weight: 1,
      },
    ],
  });

  await page.goto('/shift-counts');
  await openAddForm(page, 'Add Shift Count', 'Add New Shift Count');
  await page.getByPlaceholder('e.g., Working shifts should be close to the average').fill('Unsaved count draft');
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Existing count copy');
  await expectAddFormDismissed(page, 'e.g., Working shifts should be close to the average', 'Unsaved count draft');
  await expect(page.getByText('Existing count copy', { exact: true })).toBeVisible();

  await page.goto('/shift-type-requirements');
  await openAddForm(page, 'Add Requirement', 'Add New Requirement');
  await page.getByPlaceholder('e.g., Night shifts need senior nurses').fill('Unsaved requirement draft');
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Existing requirement copy');
  await expectAddFormDismissed(page, 'e.g., Night shifts need senior nurses', 'Unsaved requirement draft');
  await expect(page.getByText('Existing requirement copy', { exact: true })).toBeVisible();

  await page.goto('/shift-type-successions');
  await openAddForm(page, 'Add Succession', 'Add New Succession');
  await page.getByPlaceholder('e.g., Forbid Evening -> Day succession').fill('Unsaved succession draft');
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Existing succession copy');
  await expectAddFormDismissed(page, 'e.g., Forbid Evening -> Day succession', 'Unsaved succession draft');
  await expect(page.getByText('Existing succession copy', { exact: true })).toBeVisible();

  await page.goto('/shift-affinities');
  await openAddForm(page, 'Add Shift Affinity', 'Add New Shift Affinity');
  await page.getByPlaceholder('e.g., Encourage newcomers and seniors to work together').fill('Unsaved affinity draft');
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await waitForStoredCurrentSchedulingData(page, 'Existing affinity copy');
  await expectAddFormDismissed(page, 'e.g., Encourage newcomers and seniors to work together', 'Unsaved affinity draft');
  await expect(page.getByText('Existing affinity copy', { exact: true })).toBeVisible();

  await page.goto('/export-layout');
  await openAddForm(page, 'Add Export Rule', 'Add Export Rule');
  await page.getByPlaceholder('Optional note for this export rule').fill('Unsaved export draft');
  const styleRules = page.getByRole('heading', { name: 'Style Rules', exact: true }).locator('xpath=ancestor::div[contains(@class,"bg-white")][1]');
  await styleRules.getByRole('button', { name: 'Duplicate' }).first().click();
  await waitForStoredCurrentSchedulingData(page, 'Style day cells copy');
  await expectAddFormDismissed(page, 'Optional note for this export rule', 'Unsaved export draft');
  await expect(styleRules.getByText('Style day cells copy', { exact: true })).toBeVisible();
});
