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

import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, test } from './test';
import { disableModalDialogs, seedSchedulingState } from './helpers';

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

  let submittedBody = '';
  const server = createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Expose-Headers': 'Content-Disposition, X-Schedule-Score, X-Schedule-Status',
      });
      res.end();
      return;
    }

    if (req.method === 'POST' && req.url === '/optimization-jobs') {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }
      submittedBody = Buffer.concat(chunks).toString('utf8');

      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify({ job_id: 'http-test-job' }));
      return;
    }

    if (req.method === 'GET' && req.url === '/optimization-jobs/http-test-job/events') {
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      });
      res.end(
        'event: completed\n'
        + 'data: {"type":"completed","code":"completed","message":"Optimization completed","progress":1,"score":99}\n\n'
      );
      return;
    }

    if (req.method === 'GET' && req.url === '/optimization-jobs/http-test-job/result') {
      res.writeHead(200, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Content-Disposition, X-Schedule-Score, X-Schedule-Status',
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename="schedule-http.xlsx"',
        'X-Schedule-Score': '99',
        'X-Schedule-Status': 'OPTIMAL',
      });
      res.end('fake-xlsx');
      return;
    }

    res.writeHead(404).end('Not Found');
  });

  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;

  try {
    await page.goto('/optimize-and-export');
    await expect(page.getByRole('heading', { name: 'Optimize and Export', exact: true })).toBeVisible();
    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toHaveCount(0);
    await expect(page.locator('pre')).toContainText('http server optimize seed');

    await page.getByPlaceholder('http://localhost:8000').fill(`http://127.0.0.1:${port}`);
    await page.getByRole('button', { name: 'Optimize and Download' }).click();

    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
    await expect(page.getByText('File: schedule-http.xlsx')).toBeVisible();
    await expect(page.getByText('Score: 99')).toBeVisible();
    await expect(page.getByText('Status: OPTIMAL')).toBeVisible();
    expect(submittedBody).toContain('yaml_content');
    expect(submittedBody).toContain('apiVersion: test');
    expect(submittedBody).toContain('description: http server optimize seed');
  } finally {
    await new Promise<void>((resolve, reject) => server.close(error => (error ? reject(error) : resolve())));
  }
});
