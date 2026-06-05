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

import { Page } from '@playwright/test';

const STORAGE_KEY = 'nurse-scheduling-data';
const WORKER_NAMESPACE_KEY = '__PLAYWRIGHT_WORKER_NAMESPACE__';

type StoredState = {
  apiVersion: string;
  description: string;
  dates: {
    range: {
      startDate?: string;
      endDate?: string;
    };
    groups: Array<{ id: string; members: string[]; description: string }>;
  };
  people: {
    items: Array<{ id: string; description: string; history: string[] }>;
    groups: Array<{ id: string; members: string[]; description: string }>;
    history: string[];
  };
  shiftTypes: {
    items: Array<{ id: string; description: string }>;
    groups: Array<{ id: string; members: string[]; description: string }>;
  };
  preferences: Array<Record<string, unknown>>;
  export: {
    formatting: Array<Record<string, unknown>>;
  };
};

export async function seedSchedulingState(page: Page, state: StoredState) {
  const persisted = JSON.stringify({
    state,
    history: [state],
    currentHistoryIndex: 0,
  });

  await page.goto('/');
  await page.evaluate(
    ({ key, value, workerNamespaceKey }) => {
      // Mirror the app's worker-local storage key so seeded state lands in the
      // same bucket that the hook reads during the test run.
      const workerNamespace = (window as unknown as { [key: string]: string | undefined })[workerNamespaceKey];
      const storageKey = workerNamespace ? `${key}__${workerNamespace}` : key;
      window.localStorage.setItem(storageKey, value);
    },
    { key: STORAGE_KEY, value: persisted, workerNamespaceKey: WORKER_NAMESPACE_KEY }
  );
}

export async function disableModalDialogs(page: Page) {
  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });
}

type MockOptimizeAndExportOptions = {
  status?: number;
  errorDetail?: string;
  filename?: string;
  score?: number;
  solverStatus?: string;
  xlsxReady?: boolean;
  body?: string;
  onSubmit?: (body: string) => void;
};

export async function mockOptimizeAndExport(
  page: Page,
  {
    status = 200,
    errorDetail = 'solver unavailable',
    filename,
    score = 99,
    solverStatus = 'OPTIMAL',
    xlsxReady = true,
    body = 'fake-xlsx',
    onSubmit,
  }: MockOptimizeAndExportOptions = {},
) {
  const jobId = 'e2e-job';

  await page.addInitScript(() => {
    Object.defineProperty(window, 'EventSource', {
      configurable: true,
      value: undefined,
    });
  });

  await page.route('http://localhost:8000/optimize', async route => {
    const request = route.request();

    if (request.method() !== 'POST') {
      await route.fallback();
      return;
    }

    onSubmit?.((await request.postData()) ?? '');

    if (status >= 400) {
      await route.fulfill({
        status,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detail: errorDetail }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jobId,
        status: 'queued',
        score: null,
        solverStatus: null,
        error: null,
        xlsxReady: false,
        links: {
          status: `/optimize/${jobId}`,
          events: `/optimize/${jobId}/events`,
          xlsx: `/optimize/${jobId}/xlsx`,
        },
      }),
    });
  });

  await page.route(`http://localhost:8000/optimize/${jobId}`, async route => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204 });
      return;
    }

    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jobId,
        status: xlsxReady ? 'optimal' : 'infeasible',
        score,
        solverStatus,
        error: null,
        xlsxReady,
        links: {
          status: `/optimize/${jobId}`,
          events: `/optimize/${jobId}/events`,
          xlsx: `/optimize/${jobId}/xlsx`,
        },
      }),
    });
  });

  await page.route(`http://localhost:8000/optimize/${jobId}/xlsx`, async route => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    };

    if (filename) {
      headers['Content-Disposition'] = `attachment; filename="${filename}"`;
    }

    await route.fulfill({
      status: 200,
      headers,
      body,
    });
  });
}

export async function setDateRange(
  page: Page,
  startDate = '2026-05-01',
  endDate = '2026-05-01',
) {
  await page.goto('/dates');
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill(startDate);
  await page.locator('#endDate').fill(endDate);
  await page.getByRole('button', { name: /Apply|Update/ }).click();
}
