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
import { mockOptimizeAndExport, seedScheduleSpecState } from './helpers';

const RUNNING_MESSAGE = 'The optimization keeps running and downloads the schedule when it finishes, '
  + 'but this page stops showing its progress. Leave this page?';

test('optimize and export warns before leaving the page while an optimization runs', async ({ page }) => {
  /*
   * Steps:
   * 1. Start an optimization that stays running until the test releases it.
   * 2. Dismiss the tab switch and page close warnings, and confirm that the page stays open.
   * 3. Let the run finish, and confirm that switching tabs no longer asks.
   */
  await seedScheduleSpecState(page, {
    apiVersion: 'test',
    description: 'optimize leave warning seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });
  await mockOptimizeAndExport(page);
  let holdRun = true;
  // Playwright tries the latest route first, so this route keeps the mocked job running.
  await page.route('http://localhost:8000/optimize/e2e-job', async route => {
    if (!holdRun || route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      headers: { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: 'e2e-job',
        state: 'running',
        terminal: false,
        queue_position: null,
        result: null,
        error: null,
        controls: { cancellable: true, early_completion_available: false },
        links: {
          self: '/optimize/e2e-job',
          events: '/optimize/e2e-job/events',
          cancellation: '/optimize/e2e-job/cancel',
          early_completion: '/optimize/e2e-job/finish-now',
          schedule: null,
        },
      }),
    });
  });

  await page.goto('/optimize-and-export');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByRole('button', { name: 'Optimizing...' })).toBeVisible();

  const dialogs: string[] = [];
  page.once('dialog', async dialog => {
    dialogs.push(`${dialog.type()}: ${dialog.message()}`);
    await dialog.dismiss();
  });
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect.poll(() => dialogs).toEqual([`confirm: ${RUNNING_MESSAGE}`]);
  await expect(page).toHaveURL(/\/optimize-and-export$/);

  page.once('dialog', async dialog => {
    dialogs.push(dialog.type());
    await dialog.dismiss();
  });
  await page.close({ runBeforeUnload: true });
  await expect.poll(() => dialogs).toEqual([`confirm: ${RUNNING_MESSAGE}`, 'beforeunload']);
  expect(page.isClosed()).toBe(false);

  holdRun = false;
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();

  let askedAfterRun = false;
  page.on('dialog', async dialog => {
    askedAfterRun = true;
    await dialog.accept();
  });
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect(page).toHaveURL(/\/dates$/);
  expect(askedAfterRun).toBe(false);
});
