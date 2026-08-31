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

const BACKEND_URL = 'http://localhost:8000';
const BACKEND_TOKEN = 'e2e-shared-backend-token';
const STORAGE_KEY = 'nurse-scheduling-optimize-server-options';

const seedMinimalSchedule = (page: Parameters<typeof seedSchedulingState>[0]) => seedSchedulingState(page, {
  apiVersion: 'test',
  description: 'optimize auth seed',
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

test('optimize and export authenticates a protected backend with a remembered token', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and a backend that requires a shared token.
   * 2. Confirm the page reports that credentials are required and blocks optimizing.
   * 3. Enter the token and keep it on this device.
   * 4. Confirm the backend comes online, the run succeeds, and the token is stored.
   */
  await disableModalDialogs(page);
  await seedMinimalSchedule(page);
  await mockOptimizeAndExport(page, { requiredAuthToken: BACKEND_TOKEN });

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Server: Credentials required')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Optimize and Download' })).toBeDisabled();

  await page.getByRole('button', { name: `Enter token for ${BACKEND_URL}` }).click();
  await page.getByLabel(`Token for ${BACKEND_URL}`, { exact: true }).fill(BACKEND_TOKEN);
  await page.getByRole('checkbox', { name: /remember on this device/i }).check();
  await page.getByRole('button', { name: `Save token for ${BACKEND_URL}` }).click();

  await expect(page.getByText('Server: Online')).toBeVisible();
  await expect(page.getByText('Token saved on this device')).toBeVisible();

  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();

  const storedServers = await page.evaluate(
    (key) => JSON.parse(window.localStorage.getItem(key) ?? '{}').servers,
    STORAGE_KEY
  );
  expect(storedServers).toEqual([{ endpoint: BACKEND_URL, token: BACKEND_TOKEN }]);
});

test('optimize and export keeps the backend table status and actions columns visible', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a backend that requires a shared token so the credential row is rendered.
   * 2. Measure the backend table at a wide and a narrow viewport.
   * 3. Confirm the table never scrolls horizontally and the trailing columns stay in view.
   */
  await disableModalDialogs(page);
  await seedMinimalSchedule(page);
  await mockOptimizeAndExport(page, { requiredAuthToken: BACKEND_TOKEN });

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Server: Credentials required')).toBeVisible();

  for (const width of [1280, 1024, 800]) {
    await page.setViewportSize({ width, height: 900 });
    const layout = await page.evaluate(() => {
      const table = [...document.querySelectorAll('table')].find(
        candidate => candidate.textContent?.includes('Activity')
      );
      if (!table) {
        throw new Error('Backend table was not found');
      }
      const scroller = table.closest('[class*="overflow-auto"]') as HTMLElement;
      const headers = [...table.querySelectorAll('thead th')];
      const last = headers[headers.length - 1].getBoundingClientRect();
      const secondLast = headers[headers.length - 2].getBoundingClientRect();
      const bounds = scroller.getBoundingClientRect();
      return {
        scrollable: scroller.scrollWidth > scroller.clientWidth + 1,
        lastWithin: Math.round(last.right) <= Math.round(bounds.right) + 1,
        secondLastWithin: Math.round(secondLast.right) <= Math.round(bounds.right) + 1,
      };
    });

    expect(layout, `viewport ${width}`).toEqual({
      scrollable: false,
      lastWithin: true,
      secondLastWithin: true,
    });
  }
});

test('optimize and export distinguishes a rejected token from a missing one', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a stored token that the backend refuses.
   * 2. Confirm the Status icon reports a rejection through its hover text.
   * 3. Clear the token and confirm the icon falls back to the missing-token state.
   */
  await disableModalDialogs(page);
  await seedMinimalSchedule(page);
  await page.addInitScript(({ key, value }) => window.localStorage.setItem(key, value), {
    key: STORAGE_KEY,
    value: JSON.stringify({
      appVersion: 'e2e',
      servers: [{ endpoint: BACKEND_URL, token: 'stale-token' }],
      selectedServerEndpoint: 'auto',
    }),
  });
  await mockOptimizeAndExport(page, { requiredAuthToken: BACKEND_TOKEN, seedLocalBackend: false });

  await page.goto('/optimize-and-export');

  const status = page.getByLabel(`${BACKEND_URL} status: Credentials rejected`);
  await expect(status).toHaveAttribute(
    'title',
    'Backend rejected this token. Select Change to enter the current one.'
  );
  // The description line stays short so the trailing columns keep their place.
  await expect(page.getByText(/Last checked:.*rejected/i)).toHaveCount(0);

  // Correcting a rejected token starts from the stored value rather than a blank field.
  await page.getByRole('button', { name: `Change token for ${BACKEND_URL}` }).click();
  await expect(page.getByLabel(`Token for ${BACKEND_URL}`, { exact: true })).toHaveValue('stale-token');
  await page.getByRole('button', { name: `Cancel token for ${BACKEND_URL}` }).click();

  await page.getByRole('button', { name: `Forget token for ${BACKEND_URL}` }).click();
  await expect(page.getByLabel(`${BACKEND_URL} status: Credentials required`)).toHaveAttribute(
    'title',
    'This backend requires a token. Select Enter token to continue.'
  );
});

test('optimize and export completes a bare domain into an https backend URL', async ({ page }) => {
  /*
   * Steps:
   * 1. Open the page with the mocked local backend.
   * 2. Add a backend by typing only a domain name into the real inline editor.
   * 3. Confirm the stored and displayed URL gained an https scheme.
   */
  await disableModalDialogs(page);
  await seedMinimalSchedule(page);
  await mockOptimizeAndExport(page);

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Server: Online')).toBeVisible();

  await page.getByText('Double-click to add URL').dblclick();
  await page.getByPlaceholder('https://backend.example.test').fill('api.nursescheduling.org');
  await page.keyboard.press('Enter');

  await expect(page.getByTitle('https://api.nursescheduling.org')).toBeVisible();
  const storedServers = await page.evaluate(
    (key) => JSON.parse(window.localStorage.getItem(key) ?? '{}').servers,
    STORAGE_KEY
  );
  expect(storedServers).toEqual([
    { endpoint: BACKEND_URL },
    { endpoint: 'https://api.nursescheduling.org' },
  ]);
});

test('optimize and export keeps a one-time token out of browser storage', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and a backend that requires a shared token.
   * 2. Enter the token without keeping it on this device.
   * 3. Confirm the run succeeds while storage keeps only the backend URL.
   */
  await disableModalDialogs(page);
  await seedMinimalSchedule(page);
  await mockOptimizeAndExport(page, { requiredAuthToken: BACKEND_TOKEN });

  await page.goto('/optimize-and-export');
  await page.getByRole('button', { name: `Enter token for ${BACKEND_URL}` }).click();
  await page.getByLabel(`Token for ${BACKEND_URL}`, { exact: true }).fill(BACKEND_TOKEN);
  await page.getByRole('button', { name: `Save token for ${BACKEND_URL}` }).click();

  await expect(page.getByText('Token set for this session')).toBeVisible();
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();

  const storedServers = await page.evaluate(
    (key) => JSON.parse(window.localStorage.getItem(key) ?? '{}').servers,
    STORAGE_KEY
  );
  expect(storedServers).toEqual([{ endpoint: BACKEND_URL }]);
});

test('optimize and export stays unchanged against a backend without authentication', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and an open backend.
   * 2. Confirm no credential controls appear and the run succeeds directly.
   */
  await disableModalDialogs(page);
  await seedMinimalSchedule(page);
  await mockOptimizeAndExport(page);

  await page.goto('/optimize-and-export');
  await expect(page.getByText('Server: Online')).toBeVisible();
  await expect(page.getByRole('button', { name: `Enter token for ${BACKEND_URL}` })).toHaveCount(0);

  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
});
