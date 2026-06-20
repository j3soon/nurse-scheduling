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

import { expect, Page } from '@playwright/test';
import ExcelJS from 'exceljs';

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
    items?: Array<{ id: string; description: string }>;
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
    extraColumns?: Array<Record<string, unknown>>;
    extraRows?: Array<Record<string, unknown>>;
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
      window.localStorage.setItem(key, value);
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
  body?: Buffer;
  disableEventSource?: boolean;
  onSubmit?: (body: string) => void;
};

export async function createMockXlsxBuffer(): Promise<Buffer> {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Schedule');

  worksheet.getCell('A1').value = 'Nurse Scheduling';
  worksheet.getCell('A2').value = 'Generated for browser tests';
  worksheet.getCell('A3').value = 'P1';
  worksheet.getCell('B3').value = 'D';

  const buffer = await workbook.xlsx.writeBuffer();
  if (buffer instanceof ArrayBuffer) {
    return Buffer.from(buffer);
  }
  return Buffer.from(buffer);
}

export async function mockOptimizeAndExport(
  page: Page,
  {
    status = 200,
    errorDetail = 'solver unavailable',
    filename,
    score = 99,
    solverStatus = 'OPTIMAL',
    xlsxReady = true,
    body,
    disableEventSource = true,
    onSubmit,
  }: MockOptimizeAndExportOptions = {},
) {
  const jobId = 'e2e-job';
  const xlsxBody = body ?? (await createMockXlsxBuffer());

  if (disableEventSource) {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'EventSource', {
        configurable: true,
        value: undefined,
      });
    });
  }

  await page.route('http://localhost:8000/health', async route => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        status: 'ok',
        version: 'test',
        apiVersion: 'test',
        appVersion: 'test',
      }),
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
      body: xlsxBody,
    });
  });
}

export async function disableOptimizeAnonymization(page: Page) {
  const checkbox = page.getByRole('checkbox', { name: /anonymize schedule data/i });
  await checkbox.waitFor({ state: 'visible' });
  await checkbox.evaluate((element) => {
    const input = element as HTMLInputElement;
    if (input.checked) {
      input.click();
    }
  });
  await expect(checkbox).not.toBeChecked();
}

export async function waitForStoredCurrentSchedulingData(page: Page, expectedText: string) {
  await page.waitForFunction(
    ({ key, value, workerNamespaceKey }) => {
      const workerNamespace = (window as unknown as { [key: string]: string | undefined })[workerNamespaceKey];
      const storageKey = workerNamespace ? `${key}__${workerNamespace}` : key;
      const stored = window.localStorage.getItem(storageKey) ?? window.localStorage.getItem(key);
      if (!stored) {
        return false;
      }

      try {
        const parsed = JSON.parse(stored) as { state?: unknown };
        return JSON.stringify(parsed.state ?? '').includes(value);
      } catch {
        return false;
      }
    },
    { key: STORAGE_KEY, value: expectedText, workerNamespaceKey: WORKER_NAMESPACE_KEY }
  );
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
