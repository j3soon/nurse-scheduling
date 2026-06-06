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
import { disableModalDialogs, mockOptimizeAndExport, seedSchedulingState, setDateRange } from './helpers';

test('optimize and export submits YAML to the backend and renders success metadata', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and confirm the optimize page starts with no success message.
   * 2. Mock the backend optimize endpoint and trigger the real optimize action.
   * 3. Confirm the success message, returned filename, score, and status are rendered.
   */
  await disableModalDialogs(page);
  let submittedBody = '';
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize seed',
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
  await setDateRange(page);

  await mockOptimizeAndExport(page, { onSubmit: body => { submittedBody = body; } });

  await page.goto('/optimize-and-export');
  await expect(page.getByRole('heading', { name: 'Optimize and Export', exact: true })).toBeVisible();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
  await expect(page.getByText('Current YAML Preview')).toHaveCount(0);
  await expect(page.locator('pre')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Optimize and Download' })).toBeEnabled();

  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  await expect(page.getByText('output.xlsx')).toBeVisible();
  expect(submittedBody).toContain('yaml_content');
  expect(submittedBody).toContain('2026-05-01');
  expect(submittedBody).toContain('prettify');
  expect(submittedBody).toContain('timeout');
});

test('optimize and export renders backend phase SSE messages in the event log', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and install a browser EventSource test double.
   * 2. Submit optimize through the real form while keeping EventSource enabled.
   * 3. Emit a backend phase event followed by completion.
   * 4. Confirm the page renders the backend phase message and completes the download.
   */
  await disableModalDialogs(page);
  await page.addInitScript(() => {
    class MockEventSource extends EventTarget {
      url: string;

      constructor(url: string) {
        super();
        this.url = url;
        (window as unknown as { __lastEventSource?: MockEventSource }).__lastEventSource = this;
      }

      close() {}

      emit(type: string, data: unknown) {
        this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(data) }));
      }
    }

    Object.defineProperty(window, 'EventSource', {
      configurable: true,
      value: MockEventSource,
    });
  });

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'optimize sse seed',
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
  await setDateRange(page);

  await mockOptimizeAndExport(page, { disableEventSource: false });

  await page.goto('/optimize-and-export');
  await expect(page.getByRole('button', { name: 'Optimize and Download' })).toBeEnabled();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Optimize and Download' }).click();
  await page.waitForFunction(() => Boolean((window as unknown as { __lastEventSource?: unknown }).__lastEventSource));

  await page.evaluate(() => {
    const eventSource = (window as unknown as {
      __lastEventSource?: { emit: (type: string, data: unknown) => void };
    }).__lastEventSource;

    eventSource?.emit('phase', {
      source: 'scheduler:phase',
      code: 'creating_shift_variables',
      message: 'Creating shift variables',
      elapsedSeconds: 0.12,
    });
    eventSource?.emit('complete', {
      jobId: 'e2e-job',
      status: 'optimal',
      score: 99,
      solverStatus: 'OPTIMAL',
      error: null,
      xlsxReady: true,
      links: {
        status: '/optimize/e2e-job',
        events: '/optimize/e2e-job/events',
        xlsx: '/optimize/e2e-job/xlsx',
      },
    });
  });

  await downloadPromise;
  await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
  const eventLog = page.getByTestId('optimization-events-log');
  await expect(eventLog).toContainText('phase');
  await expect(eventLog).toContainText('Creating shift variables');
});
