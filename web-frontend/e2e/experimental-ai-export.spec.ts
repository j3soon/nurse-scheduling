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

import { expect, test as base, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import reference from '../../core/tests/ai_fixtures/chat-export-archive.json';

const archiveBytes = Buffer.from(reference.zip_base64, 'base64');
interface ExportBackend {
  endpoint: string;
  requests: string[];
  saved: boolean;
  error: 'POST' | 'GET' | null;
}

const test = base.extend<{ backend: ExportBackend }>({
  backend: async ({ baseURL }, runTest) => {
    const backend: ExportBackend = { endpoint: '', requests: [], saved: true, error: null };
    // Native Chromium downloads bypass route interception. Serve real bytes over HTTP.
    const server = createServer((request, response) => {
      request.resume();
      response.setHeader('Access-Control-Allow-Origin', new URL(baseURL!).origin);
      response.setHeader('Access-Control-Allow-Credentials', 'true');
      response.setHeader('Access-Control-Allow-Headers', 'Content-Type, Last-Event-ID');
      response.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      if (request.method === 'OPTIONS') {
        response.writeHead(204).end();
        return;
      }
      const path = new URL(request.url!, 'http://127.0.0.1').pathname;
      let body: unknown;
      if (path.endsWith('/capabilities')) {
        body = {
          app_version: 'v0.4.3', saved_chat_export: backend.saved,
          session_retention_seconds: 3600, auth: { required: false, scheme: 'bearer' },
          file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000, max_bytes_per_session: 200000000 },
        };
      } else if (path.endsWith('/export')) {
        backend.requests.push(request.method!);
        if (backend.error === request.method) {
          response.statusCode = 503;
          body = { detail: 'Saved history is temporarily unavailable.' };
        } else if (request.method === 'POST') body = { download_token: null };
        else {
          response.writeHead(200, { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="complete-chat.zip"' }).end(archiveBytes);
          return;
        }
      } else if (path.endsWith('/sessions')) {
        response.statusCode = 201;
        body = { id: 'export-session' };
      } else if (path.endsWith('/uploads')) body = [];
      else if (path.endsWith('/events')) {
        response.writeHead(200, { 'Content-Type': 'text/event-stream' }).end([
          'id: 1\nevent: run_start\ndata: {"run_id":"export-run","trigger":"user"}\n\n',
          'id: 2\nevent: delta\ndata: {"run_id":"export-run","text":"The server has the complete chat archive."}\n\n',
          'id: 3\nevent: done\ndata: {"run_id":"export-run"}\n\n',
        ].join(''));
        return;
      } else if (path.endsWith('/messages')) {
        response.statusCode = 202;
        body = { run_id: 'export-run' };
      } else body = { expires_in_seconds: 3600 };
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify(body));
    });
    await new Promise<void>((resolve, reject) => {
      server.once('error', reject);
      server.listen(0, '127.0.0.1', resolve);
    });
    backend.endpoint = `http://127.0.0.1:${(server.address() as AddressInfo).port}/ai`;
    try {
      await runTest(backend);
    } finally {
      const closed = new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
      server.closeAllConnections();
      await closed;
    }
  },
});
test.use({ timezoneId: 'Pacific/Honolulu', locale: 'zh-TW' });

async function openChat(page: Page, backend: ExportBackend, options: { saved?: boolean; error?: 'POST' | 'GET' } = {}) {
  backend.saved = options.saved ?? true;
  backend.error = options.error ?? null;
  await page.addInitScript(endpoint => localStorage.setItem('nurse-scheduling-ai-server', endpoint), backend.endpoint);
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Export the saved chat.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('The server has the complete chat archive.')).toBeVisible();
  return backend.requests;
}

test('one Export Chat control downloads the server ZIP without changing its bytes', async ({ page, backend }) => {
  const requests = await openChat(page, backend);
  const popup = page.context().waitForEvent('page');
  const download = popup.then(tab => tab.waitForEvent('download'));
  await page.getByRole('button', { name: 'Export Chat', exact: true }).click();
  const delivered = await download;
  expect(delivered.url()).toBe(`${backend.endpoint}/sessions/export-session/export`);
  expect(delivered.suggestedFilename()).toBe('complete-chat.zip');
  expect((await readFile((await delivered.path())!)).equals(archiveBytes)).toBe(true);
  expect(requests).toEqual(['POST', 'GET']);
  await expect(page.getByRole('button', { name: 'HTML', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Markdown', exact: true })).toHaveCount(0);
});

test('an export preparation failure keeps the chat available for retry', async ({ page, backend }) => {
  await openChat(page, backend, { error: 'POST' });
  const popup = page.context().waitForEvent('page');
  await page.getByRole('button', { name: 'Export Chat', exact: true }).click();
  await expect(page.getByText('Saved history is temporarily unavailable.')).toBeVisible();
  await expect(page.getByText('The server has the complete chat archive.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export Chat', exact: true })).toBeEnabled();
  await expect.poll(() => popup.then(tab => tab.isClosed())).toBe(true);
});

test('a native export GET failure appears in its tab and leaves the chat available', async ({ page, backend }) => {
  const requests = await openChat(page, backend, { error: 'GET' });
  const popup = page.context().waitForEvent('page');
  await page.getByRole('button', { name: 'Export Chat', exact: true }).click();
  const tab = await popup;
  await expect(tab.locator('body')).toContainText('Saved history is temporarily unavailable.');
  expect(requests).toEqual(['POST', 'GET']);
  await expect(page.getByText('The server has the complete chat archive.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export Chat', exact: true })).toBeEnabled();
});

test('export is unavailable when the server does not retain saved history', async ({ page, backend }) => {
  const requests = await openChat(page, backend, { saved: false });
  await expect(page.getByRole('button', { name: 'Export Chat', exact: true })).toBeDisabled();
  expect(requests).toEqual([]);
});

test('bundled Python HTML remains readable at desktop and phone widths', async ({ page }) => {
  await page.setContent(reference.html);
  await expect(page.locator('script')).toHaveCount(0);
  // The Session files index links the same file, so name the uploaded-file entry exactly.
  await expect(page.getByRole('link', { name: 'staff.csv (1 KB)', exact: true })).toHaveAttribute('href', /^attachments\//);
  await expect(page.getByText('Stopped before completion.')).toBeVisible();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const optimizer = page.locator('article.optimizer').first();
    await expect(optimizer).toContainText('Final score:');
    expect(await optimizer.locator('dl').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    for (const timestamp of await page.locator('article time').all()) {
      await expect(timestamp).toContainText('UTC');
      const contrast = await timestamp.evaluate(element => {
        const luminance = (color: string) => {
          const rgb = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(channel => channel / 255);
          const linear = rgb.map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
          return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
        };
        const foreground = luminance(getComputedStyle(element).color);
        const background = luminance(getComputedStyle(element.closest('article')!).backgroundColor);
        return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
      });
      expect(contrast).toBeGreaterThanOrEqual(4.5);
    }
    await expect(optimizer.getByText('Final score:', { exact: true })).toHaveCSS('font-weight', '600');
  }
});
