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

import { Page, Request } from '@playwright/test';

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

type MockOptimizationJobFlowOptions = {
  onCreateJob?: (request: Request) => Promise<void> | void;
  createStatus?: number;
  createBody?: unknown;
  filename?: string;
  resultBody?: string;
  score?: string;
  status?: string;
  jobStatus?: 'running' | 'completed' | 'failed';
};

export async function mockOptimizationJobFlow(page: Page, options: MockOptimizationJobFlowOptions = {}) {
  let jobCount = 0;
  const filename = options.filename ?? 'output.xlsx';
  const score = options.score ?? '0';
  const status = options.status ?? 'OPTIMAL';
  const jobStatus = options.jobStatus ?? 'completed';

  await page.route('http://localhost:8000/optimization-jobs', async route => {
    await options.onCreateJob?.(route.request());

    if (options.createStatus && options.createStatus >= 400) {
      await route.fulfill({
        status: options.createStatus,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options.createBody ?? { detail: 'Optimization failed' }),
      });
      return;
    }

    jobCount += 1;
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: `test-job-${jobCount}` }),
    });
  });

  await page.route(/http:\/\/localhost:8000\/optimization-jobs\/[^/]+\/events$/, async route => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
      body: [
        'event: phase\ndata: {"type":"phase","code":"loading_scenario","message":"Loading scenario","progress":0.1}\n\n',
        `event: completed\ndata: {"type":"completed","code":"completed","message":"Optimization completed","progress":1,"score":${score}}\n\n`,
      ].join(''),
    });
  });

  await page.route(/http:\/\/localhost:8000\/optimization-jobs\/[^/]+\/result$/, async route => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': `attachment; filename="${filename}"`,
        'X-Schedule-Score': score,
        'X-Schedule-Status': status,
      },
      body: options.resultBody ?? 'fake-xlsx',
    });
  });

  await page.route(/http:\/\/localhost:8000\/optimization-jobs\/[^/]+\/status$/, async route => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        status: jobStatus,
        score,
        solver_status: status,
        error: jobStatus === 'failed' ? 'Optimization failed' : null,
        filename,
      }),
    });
  });
}
