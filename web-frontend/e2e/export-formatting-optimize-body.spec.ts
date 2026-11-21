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

import yaml from 'js-yaml';
import { expect, test } from './test';
import { disableModalDialogs, mockOptimizeAndExport, seedScheduleSpecState } from './helpers';

test('custom rules and Defaults keep their order in saved and optimizer YAML', async ({ page }) => {
  await disableModalDialogs(page);
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'formatting body seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
  });

  await page.goto('/save-and-load');
  await expect(page.locator('pre')).not.toContainText('export:');
  await page.goto('/export-layout');
  await expect(page.getByRole('heading', { name: 'Defaults', exact: true })).toHaveCount(3);
  const columns = page.locator('div.bg-white').filter({
    has: page.getByRole('heading', { name: 'Extra Columns', exact: true }),
  });
  await columns.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(columns.getByRole('heading', { name: 'Defaults', exact: true })).toHaveCount(0);
  await columns.getByRole('button', { name: 'Add Defaults', exact: true }).click();
  await expect(columns.getByRole('heading', { name: 'Defaults', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add Export Rule' }).click();
  await page.getByRole('main').locator('select').nth(1).selectOption('cell');
  await page.getByRole('checkbox', { name: 'P1', exact: true }).check();
  await page.getByRole('checkbox', { name: '01', exact: true }).check();
  await page.getByRole('checkbox', { name: 'D', exact: true }).check();
  await page.getByTitle('Enter background color in hex').fill('#00ff00');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  const defaults = page.locator('[draggable="true"]').first();
  const custom = page.locator('[draggable="true"]').filter({ hasText: 'Background: #00ff00' });
  await expect(custom).toBeVisible();
  const targetY = await custom.evaluate(card => card.getBoundingClientRect().height * 0.75);
  await defaults.dragTo(custom, { targetPosition: { x: 30, y: targetY } });
  await expect(page.locator('[draggable="true"]').first()).toContainText('Background: #00ff00');

  await page.goto('/save-and-load');
  const saved = yaml.load(await page.locator('pre').innerText()) as { export: unknown };
  expect(saved.export).toEqual({
    formatting: [
      expect.objectContaining({ type: 'cell', backgroundColor: '#00ff00' }),
      { type: 'defaults' },
    ],
    extraColumns: [{ type: 'defaults' }],
    extraRows: [{ type: 'defaults' }],
  });

  let submittedBody = '';
  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  expect(submittedBody.match(/type: defaults/g)).toHaveLength(3);
  expect(submittedBody).toMatch(/backgroundColor:[^\n]*00ff00[\s\S]*type: defaults/);
  expect(submittedBody).toContain('backgroundColor');
  expect(submittedBody).toContain('00ff00');
  expect(submittedBody).toContain('shiftTypes');
  expect(submittedBody).toContain('D');
});
