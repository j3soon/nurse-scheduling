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
import { disableModalDialogs, mockOptimizeAndExport, seedSchedulingState } from './helpers';

test('optimize and export renders backend errors without a stale success state', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and confirm no prior error or success message is visible.
   * 2. Mock a backend failure from the optimize endpoint and trigger the real optimize action.
   * 3. Confirm the page shows the backend error and does not render the success state.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize error seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  await mockOptimizeAndExport(page, { status: 500, errorDetail: 'solver unavailable' });

  await page.goto('/optimize-and-export');
  await expect(page.getByRole('heading', { name: 'Optimize and Export', exact: true })).toBeVisible();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
  await expect(page.getByText('Server error (500): solver unavailable')).toHaveCount(0);

  await page.getByRole('button', { name: 'Optimize and Download' }).click();

  await expect(page.getByText('Server error (500): solver unavailable')).toBeVisible();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
});

test('allows an explicitly selected incompatible backend with a warning', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a valid schedule and return reachable backend information for an unsupported API version.
   * 2. Confirm Auto declines the backend while preserving its activity and compatibility details.
   * 3. Select the backend explicitly and confirm the warning action sends the request.
   */
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'incompatible backend seed',
    dates: {
      range: { startDate: '2026-05-01', endDate: '2026-05-01' },
      items: [{ id: '01', description: '' }],
      groups: [],
    },
    people: {
      items: [{ id: 'P1', description: 'Primary nurse', history: [] }],
      groups: [],
      history: [],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }],
      groups: [],
    },
    preferences: [],
    export: { formatting: [] },
  });

  let optimizeRequested = false;
  await page.route('http://localhost:8000/info', async route => {
    await route.fulfill({
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        status: 'ready',
        service_name: 'nurse-scheduling-api',
        api_version: 'alpha',
        app_version: 'old-backend',
        jobs: { running: 1, queued: 3, cancelling: 1 },
        workers: { online: 2 },
      }),
    });
  });
  await page.route('http://localhost:8000/optimize', async route => {
    optimizeRequested = true;
    await route.fulfill({
      status: 422,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: 'old API rejected request' }),
    });
  });

  await page.goto('/optimize-and-export');

  await expect(page.getByText('Server: Incompatible')).toBeVisible();
  await expect(page.getByText('2 active · 3 queued')).toBeVisible();
  await expect(page.getByText('2 workers')).toBeVisible();
  await expect(page.getByLabel('http://localhost:8000 status: Incompatible')).toHaveAttribute('title', 'Incompatible');
  await expect(page.getByText(/auto found no compatible backend/i)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Optimize and Download' })).toBeDisabled();
  await expect(page.getByText(/API version: alpha \(expected 0\.2\.0\)/i)).toHaveCount(0);

  await page.getByLabel('Select http://localhost:8000').check({ force: true });

  await expect(page.getByText(/API version: alpha \(expected 0\.2\.0\).*Frontend version:/i)).toBeVisible();
  await expect(page.getByText('Incompatible backend. The request may fail.')).toBeVisible();
  const optimizeButton = page.getByRole('button', { name: 'Optimize Anyway and Download' });
  await expect(optimizeButton).toBeEnabled();
  await optimizeButton.click();

  await expect(page.getByText('Server error (422): old API rejected request')).toBeVisible();
  expect(optimizeRequested).toBe(true);
});
