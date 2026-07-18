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

import { createServer, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, test } from './test';
import { createMockXlsxBuffer, disableModalDialogs, seedSchedulingState, setDateRange } from './helpers';

test('optimize and export works against a real local HTTP server instead of Playwright route mocking', async ({ page }) => {
  /*
   * Steps:
   * 1. Seed a minimal valid schedule and confirm the optimize page starts clean.
   * 2. Start a lightweight local HTTP server and point the page at that endpoint.
   * 3. Trigger optimize through the real browser fetch path.
   * 4. Confirm the server received the YAML and the page rendered the returned metadata.
   */
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'http server optimize seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });
  await setDateRange(page);

  let submittedBody = '';
  const xlsxBody = await createMockXlsxBuffer();
  const server = createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Expose-Headers': 'Content-Disposition',
      });
      res.end();
      return;
    }

    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify({
        status: 'ok',
        version: 'alpha',
        apiVersion: 'alpha',
        appVersion: 'v-test',
      }));
      return;
    }

    if (req.method === 'POST' && req.url === '/optimize') {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }
      submittedBody = Buffer.concat(chunks).toString('utf8');

      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify({
        id: 'http-job',
        state: 'queued',
        terminal: false,
        queue_position: 1,
        result: null,
        error: null,
        controls: { cancellable: true, early_completion_available: false },
        links: {
          self: '/optimize/http-job',
          events: '/optimize/http-job/events',
          cancellation: '/optimize/http-job/cancel',
          early_completion: '/optimize/http-job/finish-now',
          schedule: null,
        },
      }));
      return;
    }

    if (req.method === 'GET' && req.url === '/optimize/http-job') {
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify({
        id: 'http-job',
        state: 'completed',
        terminal: true,
        queue_position: null,
        result: {
          outcome: 'optimal',
          score: 99,
          solver_status: 'OPTIMAL',
          termination_reason: null,
        },
        error: null,
        controls: { cancellable: false, early_completion_available: false },
        links: {
          self: '/optimize/http-job',
          events: '/optimize/http-job/events',
          cancellation: '/optimize/http-job/cancel',
          early_completion: '/optimize/http-job/finish-now',
          schedule: '/optimize/http-job/xlsx',
        },
      }));
      return;
    }

    if (req.method === 'DELETE' && req.url === '/optimize/http-job') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
      });
      res.end();
      return;
    }

    if (req.method !== 'GET' || req.url !== '/optimize/http-job/xlsx') {
      res.writeHead(404).end('Not Found');
      return;
    }

    res.writeHead(200, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Expose-Headers': 'Content-Disposition',
      'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'Content-Disposition': 'attachment; filename="schedule-http.xlsx"',
    });
    res.end(xlsxBody);
  });

  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;

  try {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'EventSource', {
        configurable: true,
        value: undefined,
      });
    });

    await page.goto('/optimize-and-export');
    await expect(page.getByRole('heading', { name: 'Optimize and Export', exact: true })).toBeVisible();
    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
    await expect(page.getByText('Current YAML Preview')).toHaveCount(0);

    await page.getByText('Double-click to add URL').dblclick();
    await page.getByPlaceholder('https://backend.example.test').fill(`http://127.0.0.1:${port}`);
    await page.keyboard.press('Enter');

    await expect(page.getByRole('button', { name: 'Optimize and Download' })).toBeEnabled();
    await page.getByRole('button', { name: 'Optimize and Download' }).click();

    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
    await expect(page.getByText('schedule-http.xlsx')).toBeVisible();
    const liveResult = page.getByRole('heading', { name: 'Live Result' }).locator('xpath=ancestor::section');
    await expect(liveResult.getByText('99', { exact: true })).toBeVisible();
    await expect(liveResult.getByText('OPTIMAL')).toBeVisible();
    expect(submittedBody).toContain('yaml_content');
    expect(submittedBody).toContain('2026-05-01');
  } finally {
    await new Promise<void>((resolve, reject) => server.close(error => (error ? reject(error) : resolve())));
  }
});

test('EventSource replays missed events after a 10-second network outage', async ({ page, context }) => {
  await disableModalDialogs(page);
  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'http server SSE reconnect seed',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: { items: [{ id: 'P1', description: 'Primary nurse', history: [] }], groups: [], history: [] },
    shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });
  await setDateRange(page);

  const xlsxBody = await createMockXlsxBuffer();
  const receivedLastEventIds: Array<string | undefined> = [];
  const receivedCursorQueries: Array<string | null> = [];
  let eventConnections = 0;
  let submittedBytes = 0;
  let jobFetches = 0;
  let downloads = 0;
  let deletions = 0;
  let firstEventResponse: ServerResponse | null = null;

  const completedJob = {
    id: 'reconnect-job',
    state: 'completed',
    terminal: true,
    queue_position: null,
    result: {
      outcome: 'optimal',
      score: 101,
      solver_status: 'OPTIMAL',
      termination_reason: null,
    },
    error: null,
    controls: { cancellable: false, early_completion_available: false },
    links: {
      self: '/optimize/reconnect-job',
      events: '/optimize/reconnect-job/events',
      cancellation: '/optimize/reconnect-job/cancel',
      early_completion: '/optimize/reconnect-job/finish-now',
      schedule: '/optimize/reconnect-job/xlsx',
    },
  };

  const server = createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Expose-Headers': 'Content-Disposition',
      });
      res.end();
      return;
    }

    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify({
        status: 'ok',
        version: 'alpha',
        apiVersion: 'alpha',
        appVersion: 'v-test',
      }));
      return;
    }

    if (req.method === 'POST' && req.url === '/optimize') {
      for await (const chunk of req) {
        submittedBytes += Buffer.byteLength(chunk);
      }
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify({
        ...completedJob,
        state: 'queued',
        terminal: false,
        queue_position: 1,
        result: null,
        controls: { cancellable: true, early_completion_available: false },
        links: { ...completedJob.links, schedule: null },
      }));
      return;
    }

    const requestUrl = new URL(req.url ?? '/', 'http://127.0.0.1');
    if (req.method === 'GET' && requestUrl.pathname === '/optimize/reconnect-job/events') {
      eventConnections += 1;
      receivedLastEventIds.push(
        Array.isArray(req.headers['last-event-id'])
          ? req.headers['last-event-id'][0]
          : req.headers['last-event-id'],
      );
      const cursor = requestUrl.searchParams.get('last_event_id');
      receivedCursorQueries.push(cursor);
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });

      if (eventConnections === 1) {
        res.write('id: 1\nevent: job.state_changed\ndata: {"state":"running"}\n\n');
        res.write('id: 2\nevent: job.progressed\ndata: {"currentBestScore":101,"elapsedSeconds":1}\n\n');
        firstEventResponse = res;
        return;
      }

      if (cursor !== '2') {
        res.end('event: error\ndata: {"message":"missing replay cursor"}\n\n');
        return;
      }

      res.write('id: 3\nevent: job.state_changed\ndata: {"state":"completed"}\n\n');
      res.write('id: 4\nevent: job.result_available\ndata: {"outcome":"optimal","score":101}\n\n');
      res.end();
      return;
    }

    if (req.method === 'GET' && req.url === '/optimize/reconnect-job') {
      jobFetches += 1;
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify(completedJob));
      return;
    }

    if (req.method === 'GET' && req.url === '/optimize/reconnect-job/xlsx') {
      downloads += 1;
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Content-Disposition',
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename="schedule-reconnected.xlsx"',
      });
      res.end(xlsxBody);
      return;
    }

    if (req.method === 'DELETE' && req.url === '/optimize/reconnect-job') {
      deletions += 1;
      res.writeHead(204, { 'Access-Control-Allow-Origin': '*' });
      res.end();
      return;
    }

    res.writeHead(404).end('Not Found');
  });

  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;

  try {
    await page.goto('/optimize-and-export');
    await page.getByText('Double-click to add URL').dblclick();
    await page.getByPlaceholder('https://backend.example.test').fill(`http://127.0.0.1:${port}`);
    await page.keyboard.press('Enter');

    await expect(page.getByRole('button', { name: 'Optimize and Download' })).toBeEnabled();
    await page.getByRole('button', { name: 'Optimize and Download' }).click();

    const eventLog = page.getByTestId('optimization-events-log');
    await expect(eventLog).toContainText('job.progressed');
    await expect(eventLog).toContainText('Score: 101');

    await context.setOffline(true);
    firstEventResponse?.destroy();
    await expect(eventLog).toContainText('Optimization event stream disconnected');
    await page.waitForTimeout(10_000);
    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);

    await context.setOffline(false);

    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
    await expect(page.getByText('schedule-reconnected.xlsx')).toBeVisible();
    await expect(eventLog).toContainText('job.result_available');
    await expect.poll(() => deletions).toBe(1);

    expect(eventConnections).toBe(2);
    expect(receivedLastEventIds).toEqual([undefined, undefined]);
    expect(receivedCursorQueries).toEqual([null, '2']);
    expect(submittedBytes).toBeGreaterThan(0);
    expect(jobFetches).toBe(1);
    expect(downloads).toBe(1);
    expect(deletions).toBe(1);
  } finally {
    await context.setOffline(false);
    firstEventResponse?.destroy();
    await new Promise<void>((resolve, reject) => server.close(error => (error ? reject(error) : resolve())));
  }
});
