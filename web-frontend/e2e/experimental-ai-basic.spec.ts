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

import { expect, Page, test } from '@playwright/test';
import { createServer, type ServerResponse } from 'node:http';
import { readFile } from 'node:fs/promises';
import type { AddressInfo } from 'node:net';

interface CapturedRequests {
  scheduleYaml: string;
  messageBody: string;
  messageBodies: string[];
  messageContentType: string;
  uploadBody: string;
  uploadContentType: string;
  authorizationHeaders: string[];
}

function frontendOrigin(): string {
  const baseURL = test.info().project.use.baseURL;
  if (!baseURL) throw new Error('Playwright baseURL is required for the AI backend mock.');
  return new URL(baseURL).origin;
}

async function startCancelableAiBackend(retainUploads = false) {
  let hasUpload = false;
  let disconnected = false;
  let stopped = false;
  let eventResponse: ServerResponse | undefined;
  const journal: string[] = [];
  const publish = (type: string, data: Record<string, unknown>) => {
    const frame = `id: ${journal.length + 1}\nevent: ${type}\ndata: ${JSON.stringify({ ...data, run_id: 'cancel-run' })}\n\n`;
    journal.push(frame);
    eventResponse?.write(frame);
  };
  const allowedOrigin = frontendOrigin();
  const server = createServer((request, response) => {
    request.resume();
    const headers: Record<string, string> = {
      'Access-Control-Allow-Headers': 'Content-Type, Last-Event-ID',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    };
    if (request.headers.origin === allowedOrigin) {
      headers['Access-Control-Allow-Credentials'] = 'true';
      headers['Access-Control-Allow-Origin'] = allowedOrigin;
    }
    if (request.method === 'OPTIONS') {
      response.writeHead(204, headers).end();
      return;
    }
    if (request.url === '/ai/capabilities') {
      response.writeHead(200, { ...headers, 'Content-Type': 'application/json' }).end(JSON.stringify({
        file_attachments: {
          enabled: true,
          max_files: 8,
          max_bytes_per_file: 5_000_000,
          retained: retainUploads,
        },
      }));
      return;
    }
    if (request.url === '/ai/sessions') {
      response.writeHead(201, { ...headers, 'Content-Type': 'application/json' })
        .end(JSON.stringify({ id: 'cancel-session' }));
      return;
    }
    if (request.url === '/ai/sessions/cancel-session/events') {
      eventResponse = response;
      response.writeHead(200, { ...headers, 'Cache-Control': 'no-cache', 'Content-Type': 'text/event-stream' });
      response.flushHeaders();
      const cursor = Number(request.headers['last-event-id'] ?? 0);
      journal.slice(cursor).forEach(frame => response.write(frame));
      response.on('close', () => {
        if (!response.writableEnded) disconnected = true;
        if (eventResponse === response) eventResponse = undefined;
      });
      return;
    }
    if (request.url === '/ai/sessions/cancel-session/uploads') {
      if (request.method === 'POST') hasUpload = retainUploads;
      response.writeHead(request.method === 'POST' ? 201 : 200, { ...headers, 'Content-Type': 'application/json' }).end(JSON.stringify(
        hasUpload ? [{ id: 'file-1', filename: 'ward.csv', media_type: 'text/csv', bytes: 26 }] : [],
      ));
      return;
    }
    if (request.url === '/ai/sessions/cancel-session/messages') {
      response.writeHead(202, { ...headers, 'Content-Type': 'application/json' }).end(JSON.stringify({ run_id: 'cancel-run' }));
      publish('run_start', { trigger: 'user' });
      publish('tool_start', { name: 'bash', tool_call_id: 'call', arguments: JSON.stringify({ command: 'sleep 30' }) });
      return;
    }
    if (request.url === '/ai/sessions/cancel-session/stop' && request.method === 'POST') {
      stopped = true;
      response.writeHead(202, headers).end();
      publish('stopped', {});
      return;
    }
    response.writeHead(404, headers).end();
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address() as AddressInfo;

  return {
    origin: `http://127.0.0.1:${address.port}`,
    wasDisconnected: () => disconnected,
    wasStopped: () => stopped,
    close: async () => {
      const closed = new Promise<void>((resolve, reject) => {
        server.close(error => error ? reject(error) : resolve());
      });
      server.closeAllConnections();
      await closed;
    },
  };
}

async function mockAiBackend(
  page: Page,
  answerDeltas = ['The image and schedule ', 'were received.'],
  failFirstMessage = false,
  requiredAuthToken?: string,
  sessionEvents: { type: string; data: Record<string, unknown> }[] = [],
  reportContext = true,
  // Run events published before `done`, such as a generated ZIP.
  answerEvents: { type: string; data: Record<string, unknown> }[] = [],
): Promise<CapturedRequests> {
  const captured = {
    scheduleYaml: '',
    messageBody: '',
    messageBodies: [] as string[],
    messageContentType: '',
    uploadBody: '',
    uploadContentType: '',
    authorizationHeaders: [] as string[],
  };
  const allowedOrigin = frontendOrigin();
  // Like the backend, record each upload as an app event that the next request sends before the question.
  const pendingAppEvents: string[] = [];
  let historyLength = 0;
  const journal: string[] = [];
  let wakeReader: (() => void) | undefined;
  const publish = (type: string, data: Record<string, unknown>) => {
    journal.push(`id: ${journal.length + 1}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`);
  };
  sessionEvents.forEach(event => publish(event.type, event.data));

  await page.route('**/info', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ app_version: 'v0.4.3-backend' }),
  }));
  await page.route('**/ai/**', async route => {
    const request = route.request();
    const corsHeaders = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type, Last-Event-ID',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Origin': allowedOrigin,
    };
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (request.url().endsWith('/capabilities')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({
          ...(requiredAuthToken ? { auth: { required: true, scheme: 'bearer' } } : {}),
          file_attachments: {
            enabled: true,
            max_files: 8,
            max_bytes_per_file: 5_000_000,
          },
        }),
      });
      return;
    }
    const authorization = request.headers()['authorization'] ?? '';
    captured.authorizationHeaders.push(authorization);
    if (requiredAuthToken && authorization !== `Bearer ${requiredAuthToken}`) {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ detail: 'Backend credentials are invalid.' }),
      });
      return;
    }
    if (request.url().endsWith('/sessions')) {
      captured.scheduleYaml = (request.postDataJSON() as { schedule_yaml: string }).schedule_yaml;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ id: 'browser-session' }),
      });
      return;
    }
    if (request.url().endsWith('/sessions/browser-session/events')) {
      const cursor = Number(request.headers()['last-event-id'] ?? 0);
      if (journal.length <= cursor) await new Promise<void>(resolve => { wakeReader = resolve; });
      await route.fulfill({ status: 200, contentType: 'text/event-stream', headers: corsHeaders, body: journal.slice(cursor).join('') });
      return;
    }
    if (request.url().endsWith('/sessions/browser-session') && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ expires_in_seconds: 172800 }),
      });
      return;
    }

    if (request.url().endsWith('/sessions/browser-session/uploads') && request.method() === 'POST') {
      captured.uploadBody = request.postDataBuffer()?.toString('latin1') ?? '';
      captured.uploadContentType = request.headers()['content-type'] ?? '';
      const filenames = [...captured.uploadBody.matchAll(/filename="([^"]+)"/g)].map(match => match[1]);
      pendingAppEvents.push(`[App event] The user uploaded files: ${JSON.stringify(filenames)}`);
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify(filenames.map((filename, index) => ({
          id: `file-${index + 1}`, filename, media_type: 'application/octet-stream', bytes: 1,
        }))),
      });
      return;
    }

    captured.messageBody = request.postData() ?? '';
    captured.messageBodies.push(captured.messageBody);
    captured.messageContentType = request.headers()['content-type'] ?? '';
    const firstMessageFailed = failFirstMessage && captured.messageBodies.length === 1;
    const runId = `answer-${captured.messageBodies.length}`;
    publish('run_start', { run_id: runId, trigger: 'user' });
    const sent = JSON.parse(captured.messageBody || '{}') as { message?: string };
    const appEvents = pendingAppEvents.splice(0).map(content => ({
      kind: 'app', index: historyLength++, content, title: 'Files Uploaded',
    }));
    historyLength += 2;
    publish('model_input', {
      run_id: runId,
      system: 'Mock system prompt',
      messages: [...appEvents, { kind: 'question', content: sent.message }],
    });
    const frames = firstMessageFailed
        ? [
          `event: tool_start\ndata: ${JSON.stringify({ name: 'bash', arguments: '{"command":"sleep 30"}' })}\n\n`,
          'event: delta\ndata: {"text":"Provisional response."}\n\n',
          'event: error\ndata: {"message":"The temporary AI sandbox failed."}\n\n',
        ].join('')
        : [
          'event: context_usage\ndata: {"used_chars":500,"max_chars":2000}\n\n',
          ...answerDeltas.map(text => `event: delta\ndata: ${JSON.stringify({ text })}\n\n`),
          ...answerEvents.map(event => `event: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`),
          'event: done\ndata: {"run_id":"answer-id"}\n\n',
        ].join('');
    for (const frame of frames.trim().split('\n\n')) {
      const lines = frame.split('\n');
      const type = lines.find(line => line.startsWith('event: '))!.slice(7);
      if (!reportContext && type === 'context_usage') continue;
      const data = JSON.parse(lines.find(line => line.startsWith('data: '))!.slice(6));
      publish(type, { ...data, run_id: runId });
    }
    await route.fulfill({ status: 202, contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ run_id: runId }) });
    wakeReader?.();
    wakeReader = undefined;
  });

  return captured;
}

test('asks about the current schedule and renders a streamed answer', async ({ page }) => {
  const captured = await mockAiBackend(page);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who works first?');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  await expect(page.getByText('Backend v0.4.3-backend')).toBeVisible();
  await expect(page.getByText('Chat history context: 25.0%')).toBeVisible();
  const userTime = page.locator('article').filter({ hasText: 'Who works first?' }).locator('time');
  await expect(userTime).toHaveAttribute('datetime', /T/);
  await expect(userTime).toHaveAttribute('title', /\d{4}/);
  await expect(page.locator('article').filter({ hasText: 'The image and schedule were received.' }).locator('time'))
    .toHaveAttribute('title', /\d{4}/);
  const composerBox = await page.locator('main form').boundingBox();
  const viewport = page.viewportSize();
  expect(composerBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(Math.abs(composerBox!.y + composerBox!.height - viewport!.height)).toBeLessThanOrEqual(2);
  await expect(page.getByRole('contentinfo')).toHaveCount(0);
  expect(JSON.parse(captured.messageBody)).toEqual({ message: 'Who works first?', message_id: expect.any(String) });
  expect(captured.scheduleYaml).toContain('apiVersion:');

  await expect(page.getByRole('button', { name: 'Stop' })).toBeHidden();
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect(page).toHaveURL(/\/dates$/);
  await page.getByRole('button', { name: '12. Experimental AI' }).click();
  await expect(page.getByText('The image and schedule were received.')).toBeVisible();

  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Check next week.');
  page.once('dialog', async dialog => {
    expect(dialog.message()).toBe('You have unsaved edits. Leave this page without saving?');
    await dialog.dismiss();
  });
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect(page).toHaveURL(/\/experimental-ai$/);

  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect(page).toHaveURL(/\/dates$/);
});

test('explains unavailable context usage when the backend omits it', async ({ page }) => {
  await mockAiBackend(page, ['Done.'], false, undefined, [], false);
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Question');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  const usage = page.getByText('Chat history context: unavailable');
  await expect(usage).toBeVisible();
  await expect(usage).toHaveAttribute('title', /The AI server has not reported context usage/);
});

test('returns to the top of a long chat on desktop and mobile', async ({ page }) => {
  await mockAiBackend(page, [Array.from({ length: 80 }, (_, i) => `Chat line ${i + 1}.`).join('\n\n')]);
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Show details.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('Chat line 80.', { exact: true })).toBeVisible();

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 800 });
    await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight }));
    const shortcut = page.getByRole('button', { name: 'Back to top' });
    await expect(shortcut).toBeVisible();
    await shortcut.click();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await expect(shortcut).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Schedule AI Chat' })).toBeVisible();
    await page.getByRole('button', { name: 'Scroll to bottom' }).click();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(128);
  }
});

test('authenticates AI session requests with an explicitly remembered token', async ({ page }) => {
  const authToken = 'browser-ai-auth-token';
  const captured = await mockAiBackend(
    page,
    ['Authenticated response.'],
    false,
    authToken,
  );

  await page.goto('/experimental-ai');
  const composer = page.getByRole('textbox', { name: 'Ask about the current schedule' });
  await expect(composer).toBeDisabled();
  await page.getByRole('button', { name: 'Enter token for AI assistant' }).click();
  await page.getByRole('textbox', { name: 'Token for AI assistant' }).fill(authToken);
  await page.getByRole('checkbox', { name: /remember on this device/i }).check();
  await page.getByRole('button', { name: 'Save token for AI assistant' }).click();

  await expect(composer).toBeEnabled();
  await composer.fill('Use the protected service.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByText('Authenticated response.')).toBeVisible();
  expect(captured.authorizationHeaders.length).toBeGreaterThanOrEqual(2);
  expect(captured.authorizationHeaders.every(header => header === `Bearer ${authToken}`)).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem('nurse-scheduling-ai-auth'))).toBe(
    JSON.stringify({ tokens: { '/ai': authToken } }),
  );
});

test('retries a failed text run without hiding its provisional activity', async ({ page }) => {
  const captured = await mockAiBackend(
    page,
    ['Recovered response.'],
    true,
  );

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who works first?');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByText('Provisional response.')).toBeVisible();
  await expect(page.getByText('This response failed and will not be used as context for future messages.')).toBeVisible();
  await page.getByText('bash · interrupted').click();
  await expect(page.getByText('{"command":"sleep 30"}', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry' }).click();

  await expect(page.getByText('Recovered response.')).toBeVisible();
  const bodies = captured.messageBodies.map(body => JSON.parse(body));
  expect(bodies).toEqual([
    { message: 'Who works first?', message_id: expect.any(String) },
    { message: 'Who works first?', message_id: expect.any(String) },
  ]);
  // A retry asks again, so it is a new message rather than a reconnect to the failed run.
  expect(bodies[0].message_id).not.toBe(bodies[1].message_id);
});

test('Stop cancels the run while keeping the session stream open', async ({ page }) => {
  const backend = await startCancelableAiBackend();
  for (const origin of ['null', 'https://untrusted.example']) {
    const response = await fetch(`${backend.origin}/ai/capabilities`, { headers: { Origin: origin } });
    expect(response.headers.get('access-control-allow-origin')).toBeNull();
    expect(response.headers.get('access-control-allow-credentials')).toBeNull();
  }
  await page.route('**/ai/**', route => {
    const requestUrl = new URL(route.request().url());
    return route.continue({ url: `${backend.origin}${requestUrl.pathname}${requestUrl.search}` });
  });

  try {
    await page.goto('/experimental-ai');
    await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Wait for this command.');
    await page.getByRole('button', { name: 'Send', exact: true }).click();

    await expect(page.getByText('bash · running')).toBeVisible();
    await page.getByRole('button', { name: 'Stop' }).click();

    await expect.poll(backend.wasStopped).toBe(true);
    expect(backend.wasDisconnected()).toBe(false);
    await expect(page.getByText('bash · interrupted')).toBeVisible();
    await expect(page.getByText('Stopped before completion.')).toBeVisible();
    for (const format of ['HTML', 'Markdown']) {
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: format, exact: true }).click();
      const exported = await readFile(await (await download).path(), 'utf8');
      expect(exported).toContain(format === 'HTML' ? 'Stopped before completion.' : 'Status: stopped');
      if (format === 'HTML') expect(exported).not.toContain('[No message text]');
    }
  } finally {
    await backend.close();
  }
});

test('downloads a completed background optimization from chat', async ({ page }) => {
  const workbookBytes = Buffer.from('browser-result-workbook');
  const completedRun = {
    job_id: 'opt-browser', state: 'completed', terminal: true, downloadable: true,
    result: { outcome: 'optimal', score: 0, solver_status: 'OPTIMAL', termination_reason: 'completed' },
    request: { solver: 'ortools/cp-sat', timeout_seconds: 300 },
    backend: { url: 'http://optimizer:8000', app_version: 'v0.4.3', api_version: '0.2.0', request_timeout_seconds: 30,
      claimed_performance: { score: 125, app_version: 'v0.4.2', measured_at: '2026-09-18T01:00:00Z' } },
  };
  await mockAiBackend(page, ['Optimization started.'], false, undefined, [
    { type: 'optimization', data: { job_id: 'opt-browser', state: 'running', terminal: false, downloadable: false } },
    { type: 'optimization', data: completedRun },
  ]);
  await page.route('**/ai/sessions/browser-session/optimizations/opt-browser/xlsx', route => route.fulfill({
    status: 200,
    contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    body: workbookBytes,
  }));

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Optimize it.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  const summary = page.locator('article').filter({ hasText: 'Optimization finished.' });
  await expect(summary).toContainText('Outcome: optimal');
  await expect(summary).toContainText('Final score: 0');
  await expect(summary).toContainText('Backend URL: http://optimizer:8000');
  await expect(summary).toContainText('Backend version: v0.4.3');
  await expect(summary).toContainText('Solver timeout: 300s');
  await expect(summary).toContainText('Backend request timeout: 30s');
  await expect(summary).toContainText('Claimed performance: 125');
  for (const format of ['HTML', 'Markdown']) {
    const exportedFile = page.waitForEvent('download');
    await page.getByRole('button', { name: format, exact: true }).click();
    const exportDownload = await exportedFile;
    const exported = await readFile(await exportDownload.path(), 'utf8');
    expect(exported).toContain('Frontend version:');
    expect(exported).toContain('Backend version: v0.4.3-backend');
    expect(exported).toContain(format === 'HTML' ? '<dt>Outcome:</dt> <dd>optimal</dd>' : '**Outcome:** optimal');
    expect(exported).toContain(format === 'HTML' ? '<dt>Final score:</dt> <dd>0</dd>' : '**Final score:** 0');
    expect(exported).toContain(format === 'HTML' ? '<dt>Backend URL:</dt> <dd>http://optimizer:8000</dd>' : '**Backend URL:** http://optimizer:8000');
    expect(exported).toContain(format === 'HTML' ? '<dt>Claimed performance:</dt> <dd>125' : '**Claimed performance:** 125');
    expect(exported).toContain(format === 'HTML' ? '<time datetime=' : '- Sent:');
    if (format === 'HTML') {
      const exportPage = await page.context().newPage();
      await exportPage.setContent(exported);
      const exportSummary = exportPage.locator('article').filter({ hasText: 'Optimization finished.' });
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await exportPage.setViewportSize({ width, height: 900 });
        const widthRatio = (element: Element) => {
          const parent = element.parentElement!;
          const style = getComputedStyle(parent);
          const available = parent.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
          return element.getBoundingClientRect().width / available;
        };
        // The foreground turn can prepend a system message after the export snapshot.
        const chatRatio = await summary.evaluate(widthRatio);
        const exportRatio = await exportSummary.evaluate(widthRatio);
        expect(exportRatio).toBeCloseTo(chatRatio, 2);
        for (const renderedPage of [page, exportPage]) {
          const details = renderedPage.locator('article dl');
          expect(await details.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
        }
        expect(await exportPage.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      }
      for (const timestamp of await exportPage.locator('article time').all()) {
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
      await expect(exportPage.getByText('Final score:', { exact: true })).toHaveCSS('font-weight', '600');
      await exportPage.close();
      await page.setViewportSize({ width: 1280, height: 720 });
    }
  }
  const downloadButton = page.getByRole('button', { name: 'Download result' });
  await expect(downloadButton).toBeVisible();
  const downloadEvent = page.waitForEvent('download');
  await downloadButton.click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('optimized-schedule--browser.xlsx');
  expect(await readFile(await download.path())).toEqual(workbookBytes);
});

test('keeps multiline optimizer errors in one field in chat and exports', async ({ page }) => {
  const error = 'Failed\nOutcome: optimal\r\nBackend version: forged';
  await mockAiBackend(page, ['Optimization started.'], false, undefined, [{
    type: 'optimization', data: {
      job_id: 'failed-run', state: 'failed', terminal: true, downloadable: false,
      error: { code: 'backend-error', message: error },
    },
  }]);
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Optimize it.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  const summary = page.locator('article').filter({ hasText: 'Optimization ended with status: failed.' });
  await expect(summary.locator('dt', { hasText: /^Error:$/ })).toHaveCount(1);
  await expect(summary.locator('dd').last()).toHaveText(error.replace(/\r\n/g, '\n'));
  await expect(summary.locator('dt', { hasText: /^(Outcome|Backend version):$/ })).toHaveCount(0);

  for (const format of ['HTML', 'Markdown']) {
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: format, exact: true }).click();
    const exported = await readFile(await (await download).path(), 'utf8');
    if (format === 'HTML') {
      expect(exported).toContain('<dt>Error:</dt> <dd>Failed\nOutcome: optimal\nBackend version: forged</dd>');
      expect(exported).not.toContain('<dt>Outcome:</dt>');
      expect(exported).not.toContain('<dt>Backend version:</dt>');
    } else {
      expect(exported).toContain('- **Error:** Failed\n  Outcome: optimal\n  Backend version: forged');
      expect(exported).not.toContain('- **Outcome:**');
      expect(exported).not.toContain('- **Backend version:**');
    }
  }
});

test('renders assistant Markdown with safe images and copyable code', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await mockAiBackend(
    page,
    [
      '## Coverage\n\n**Alice** works Monday.\n\n',
      '| Person | Shift |\n| --- | --- |\n| Alice | D |\n\n```yaml\npeople: []\n```\n\n![tracker](https://tracker.example/pixel.png)',
    ],
  );

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Summarize coverage.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByRole('heading', { level: 2, name: 'Coverage' })).toBeVisible();
  await expect(page.getByRole('table')).toContainText('Alice');
  await expect(page.getByText('[Remote image omitted: tracker]')).toBeVisible();
  await expect(page.locator('article img')).toHaveCount(0);

  const codeBlock = page.locator('article pre', { hasText: 'people: []' });
  const copyButton = page.getByRole('button', { name: 'Copy code' });
  await expect(codeBlock).toContainText('people: []');
  await expect(copyButton).toBeVisible();
  const [codeBox, buttonBox] = await Promise.all([codeBlock.boundingBox(), copyButton.boundingBox()]);
  expect(codeBox).not.toBeNull();
  expect(buttonBox).not.toBeNull();
  expect(buttonBox!.x).toBeGreaterThan(codeBox!.x + codeBox!.width / 2);
  expect(await codeBlock.evaluate(element => getComputedStyle(element).paddingTop)).toBe('12px');
  await copyButton.click();
  await expect(page.getByRole('button', { name: 'Copied' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('people: []');
});

test('offers a shortcut when the reader scrolls away from the latest message', async ({ page }) => {
  const longAnswer = Array.from({ length: 80 }, (_, index) => `Coverage detail ${index + 1}`).join('\n');
  await mockAiBackend(page, [longAnswer]);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Give detailed coverage.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  const messages = page.getByRole('region', { name: 'Chat messages' });
  const composer = page.getByRole('textbox', { name: 'Ask about the current schedule' });
  await expect(messages.getByText('Coverage detail 80')).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight)).toBe(true);
  await expect(composer).toBeInViewport();
  await page.mouse.move(400, 300);
  await page.mouse.wheel(0, -800);

  const scrollButton = page.getByRole('button', { name: 'Scroll to bottom' });
  await expect(scrollButton).toBeVisible();
  await expect(scrollButton).toHaveAttribute('title', 'Scroll to bottom');
  await expect(scrollButton).toHaveText('');
  await expect
    .poll(async () => {
      const buttonBox = await page.getByRole('group', { name: 'Chat navigation' }).boundingBox();
      return buttonBox ? buttonBox.x + buttonBox.width / 2 : null;
    })
    .toBe(page.viewportSize()!.width / 2);
  await expect(composer).toBeInViewport();
  const scrolledAwayY = await page.evaluate(() => window.scrollY);
  expect(await messages.evaluate(element => getComputedStyle(element).overflowY)).toBe('visible');
  await scrollButton.click();
  await expect(scrollButton).toBeHidden();
  await expect(composer).toBeInViewport();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(scrolledAwayY);
});

test('previews and sends an image attachment', async ({ page }) => {
  const captured = await mockAiBackend(page);
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );

  await page.goto('/experimental-ai');
  await page.getByLabel('Attach files').setInputFiles({ name: 'ward.png', mimeType: 'image/png', buffer: png });
  await expect(page.getByAltText('Preview of ward.png')).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('What is shown?');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  expect(captured.uploadContentType).toContain('multipart/form-data');
  expect(captured.uploadBody).toContain('filename="ward.png"');
  expect(captured.messageContentType).toBe('application/json');
  expect(JSON.parse(captured.messageBody)).toEqual({ message: 'What is shown?', message_id: expect.any(String) });
  // The bubbles follow the provider request: system prompt, upload event, then the question as typed.
  const cards = page.getByLabel('Chat messages').locator('article');
  await expect(cards.locator('> p:first-child')).toHaveText(['System', 'User · App - Files Uploaded', 'User', 'Assistant']);
  await expect(cards.nth(1)).toContainText('[App event] The user uploaded files: ["ward.png"]');
  await expect(cards.nth(2)).toContainText('What is shown?');
  const systemPrompt = cards.nth(0).locator('details');
  await expect(systemPrompt.locator('pre')).toBeHidden();
  await systemPrompt.locator('summary').click();
  await expect(systemPrompt.locator('pre')).toHaveText('Mock system prompt');
});

test('previews and sends arbitrary file attachments', async ({ page }) => {
  const captured = await mockAiBackend(page);

  await page.goto('/experimental-ai');
  await page.getByLabel('Attach files').setInputFiles([
    {
      name: 'staff.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('name,shift\nAlice,day\n'),
    },
    {
      name: 'notes.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 test'),
    },
    {
      name: 'coverage.custom',
      mimeType: 'application/x-custom',
      buffer: Buffer.from('custom test'),
    },
  ]);
  await expect(page.getByText('csv', { exact: true })).toBeVisible();
  await expect(page.getByText('pdf', { exact: true })).toBeVisible();
  await expect(page.getByText('custom', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Check the documents.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  // The upload event text starts collapsed under its titled label.
  const upload = page.getByLabel('Chat messages').locator('article', { hasText: 'User · App - Files Uploaded' });
  await expect(upload.locator('pre')).toBeHidden();
  await expect(upload).toContainText('[App event] The user uploaded files: ["staff.csv","notes.pdf","coverage.custom"]');
  expect(captured.uploadContentType).toContain('multipart/form-data');
  expect(captured.uploadBody).toContain('name="files"');
  expect(captured.uploadBody).toContain('staff.csv');
  expect(captured.uploadBody).toContain('notes.pdf');
  expect(captured.uploadBody).toContain('coverage.custom');
  expect(captured.uploadBody).toContain('Alice,day');
  expect(JSON.parse(captured.messageBody)).toEqual({ message: 'Check the documents.', message_id: expect.any(String) });
});

test('downloads and removes generated files through the ZIP controls', async ({ page }) => {
  await mockAiBackend(page, ['Files ready.'], false, undefined, [], true, [
    { type: 'download', data: { download_id: 'zip-run' } },
  ]);
  let removed = false;
  await page.route('**/ai/sessions/*/downloads/zip-run', route => {
    if (route.request().method() === 'DELETE') {
      removed = true;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ contentType: 'application/zip', body: Buffer.from('captured ZIP bytes') });
  });
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Create a downloadable CSV');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  const pendingDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download files (ZIP)' }).click();
  const download = await pendingDownload;
  expect(download.suggestedFilename()).toBe('download.zip');
  expect(await readFile((await download.path())!)).toEqual(Buffer.from('captured ZIP bytes'));
  await page.getByRole('button', { name: 'Remove ZIP' }).click();
  await expect(page.getByRole('button', { name: 'Remove ZIP' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Download files (ZIP)' })).toHaveCount(0);
  expect(removed).toBe(true);
  await expect(page.getByText('Files ready.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Files ready.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download files (ZIP)' })).toHaveCount(0);
});

test('shows retained uploads while the assistant response is still running', async ({ page }) => {
  const backend = await startCancelableAiBackend(true);
  await page.route('**/ai/**', route => {
    const requestUrl = new URL(route.request().url());
    return route.continue({ url: `${backend.origin}${requestUrl.pathname}${requestUrl.search}` });
  });
  try {
    await page.goto('/experimental-ai');
    await page.getByLabel('Attach files').setInputFiles({
      name: 'ward.csv', mimeType: 'text/csv', buffer: Buffer.from('name,date\nAlex,2026-10-01\n'),
    });
    await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Read this file');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    const panel = page.getByRole('complementary', { name: 'Session files' });
    await expect(panel.getByRole('button', { name: 'Remove ward.csv' })).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Remove ward.csv' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await expect.poll(backend.wasStopped).toBe(true);
    await expect(panel.getByRole('button', { name: 'Remove ward.csv' })).toBeEnabled();
  } finally {
    await backend.close();
  }
});

test('places uploads beside desktop chat and below mobile controls and allows removal', async ({ page }) => {
  const captured = await mockAiBackend(page, ['Workbook inspected.'], false, 'browser-ai-auth-token');
  let retained = false;
  await page.route('**/ai/capabilities', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ auth: { required: true, scheme: 'bearer' }, file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000 } }),
  }));
  await page.route('**/ai/sessions/*/uploads', route => {
    if (route.request().method() === 'POST') retained = true;
    return route.fulfill({
      contentType: 'application/json', body: JSON.stringify(retained ? [{ id: 'file-1', filename: 'ward.csv', media_type: 'text/csv', bytes: 26 }] : []),
    });
  });
  await page.route('**/ai/sessions/*/uploads/file-1', route => {
    expect(route.request().method()).toBe('DELETE');
    retained = false;
    return route.fulfill({ status: 204 });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/experimental-ai');
  await page.getByRole('button', { name: 'Enter token for AI assistant' }).click();
  await page.getByRole('textbox', { name: 'Token for AI assistant' }).fill('browser-ai-auth-token');
  await page.getByRole('button', { name: 'Save token for AI assistant' }).click();
  await page.getByLabel('Attach files').setInputFiles({ name: 'ward.csv', mimeType: 'text/csv', buffer: Buffer.from('name,date\nAlex,2026-10-01\n') });
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Read this file');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('Workbook inspected.')).toBeVisible();
  expect(JSON.parse(captured.messageBody)).toEqual({ message: 'Read this file', message_id: expect.any(String) });
  const panel = page.getByRole('complementary', { name: 'Session files' });
  await expect(panel.getByRole('button', { name: 'Remove ward.csv' })).toBeVisible();
  const panelBox = (await panel.boundingBox())!;
  const chatBox = (await page.getByRole('region', { name: 'Chat messages' }).boundingBox())!;
  expect(panelBox.x).toBeGreaterThan(chatBox.x + chatBox.width);
  for (const width of [1440, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const pageCenter = await page.evaluate(() => document.documentElement.clientWidth / 2);
    const fixedPanel = (await panel.boundingBox())!;
    for (const box of [
      (await page.getByRole('region', { name: 'Chat messages' }).boundingBox())!,
      (await page.locator('form', { has: page.getByRole('textbox', { name: 'Ask about the current schedule' }) }).boundingBox())!,
    ]) {
      expect(Math.abs(box.x + box.width / 2 - pageCenter)).toBeLessThanOrEqual(2);
      expect(box.x + box.width).toBeLessThanOrEqual(fixedPanel.x);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: '../artifacts/uploads-layout/desktop.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  const mobilePanelBox = (await panel.boundingBox())!;
  const titleBox = (await page.getByRole('heading', { name: 'Schedule AI Chat' }).boundingBox())!;
  const exportBox = (await page.getByRole('button', { name: 'Markdown', exact: true }).boundingBox())!;
  const tokenBox = (await page.getByRole('button', { name: 'Change token for AI assistant' }).boundingBox())!;
  const mobileChatBox = (await page.getByRole('region', { name: 'Chat messages' }).boundingBox())!;
  expect(mobilePanelBox.y).toBeGreaterThan(titleBox.y + titleBox.height);
  expect(mobilePanelBox.y).toBeGreaterThan(exportBox.y + exportBox.height);
  expect(mobilePanelBox.y).toBeGreaterThan(tokenBox.y + tokenBox.height);
  expect(mobilePanelBox.y + mobilePanelBox.height).toBeLessThan(mobileChatBox.y);
  await page.screenshot({
    path: '../artifacts/uploads-layout/mobile.png', fullPage: true,
    style: '[aria-label="Message composer"] { visibility: hidden !important; }',
  });
  await panel.getByText('Uploaded files (1)', { exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Remove ward.csv' })).toBeHidden();
  await panel.getByText('Uploaded files (1)', { exact: true }).click();
  await panel.getByRole('button', { name: 'Remove ward.csv' }).click();
  await expect(panel.getByText('No uploaded files.')).toBeVisible();
});

for (const { interruption, steered } of (['network pause', 'reload', 'tab switch'] as const)
  .flatMap(interruption => [false, true].map(steered => ({ interruption, steered })))) {
  test(`recovers the complete answer after a ${interruption}${steered ? ' with steering' : ''}`, async ({ page, context }) => {
    const origin = frontendOrigin();
    const authToken = 'browser-ai-auth-token';
    const messageIds: string[] = [];
    const cursors: number[] = [];
    const journal: string[] = [];
    const readers = new Set<ServerResponse>();
    let executions = 0;
    let unauthorized = 0;
    let closedReaders = 0;
    const headers = {
      'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type, Last-Event-ID',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    };
    const publish = (type: string, data: Record<string, unknown>) => {
      const frame = `id: ${journal.length + 1}\nevent: ${type}\ndata: ${JSON.stringify({ ...data, run_id: 'run-1' })}\n\n`;
      journal.push(frame);
      for (const reader of readers) reader.write(frame);
    };
    const complete = () => {
      publish('delta', { text: 'complete answer.' });
      publish('done', {});
    };
    const server = createServer(async (request, response) => {
      if (request.method === 'OPTIONS') { response.writeHead(204, headers).end(); return; }
      const json = (body: unknown, status = 200) => response.writeHead(status, { ...headers, 'Content-Type': 'application/json' }).end(JSON.stringify(body));
      if (request.url === '/ai/capabilities') {
        json({
          auth: { required: true, scheme: 'bearer' },
          file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000 },
          session_retention_seconds: 2592000,
        });
        return;
      }
      // Hosted deployments require the token on every session request, including reload recovery.
      if (request.url?.startsWith('/ai/sessions') && request.headers.authorization !== `Bearer ${authToken}`) {
        unauthorized += 1;
        request.resume();
        json({ detail: 'Backend credentials are invalid.' }, 401);
        return;
      }
      if (request.url === '/ai/sessions' && request.method === 'POST') { request.resume(); json({ id: 'replay-session' }, 201); return; }
      if (request.url === '/ai/sessions/replay-session') { json({ expires_in_seconds: 2592000 }); return; }
      if (request.url === '/ai/sessions/replay-session/uploads') { json([]); return; }
      if (request.url === '/ai/sessions/replay-session/events') {
        const cursor = Number(request.headers['last-event-id'] ?? 0);
        cursors.push(cursor);
        response.writeHead(200, { ...headers, 'Cache-Control': 'no-cache', 'Content-Type': 'text/event-stream' });
        response.flushHeaders();
        journal.slice(cursor).forEach(frame => response.write(frame));
        readers.add(response);
        response.on('close', () => { readers.delete(response); closedReaders += 1; });
        return;
      }
      if (request.url === '/ai/sessions/replay-session/messages') {
        let body = '';
        try { for await (const chunk of request) body += chunk; } catch { return; }
        const sent = JSON.parse(body) as { message_id: string };
        messageIds.push(sent.message_id);
        if (messageIds.length > 1) { json({ run_id: 'run-1' }, 202); return; }
        executions += 1;
        publish('run_start', { trigger: 'user' });
        publish('delta', { text: 'First part and ' });
        // The run is accepted, but its acknowledgement is lost. The browser asks again with the same ID.
        response.destroy();
        return;
      }
      request.resume();
      response.writeHead(404, headers).end();
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    const endpoint = `http://127.0.0.1:${(server.address() as AddressInfo).port}/ai`;
    try {
      await page.addInitScript(value => localStorage.setItem('nurse-scheduling-ai-server', value), endpoint);
      await page.goto('/experimental-ai');
      await page.getByRole('button', { name: 'Enter token for AI assistant' }).click();
      await page.getByRole('textbox', { name: 'Token for AI assistant' }).fill(authToken);
      await page.getByRole('checkbox', { name: /remember on this device/i }).check();
      await page.getByRole('button', { name: 'Save token for AI assistant' }).click();
      await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Continue while disconnected');
      await page.getByRole('button', { name: 'Send', exact: true }).click();
      await expect(page.getByText('First part and', { exact: true })).toBeVisible();
      await expect.poll(() => messageIds.length).toBe(2);
      if (steered) {
        publish('steering', { message_id: 'queued-1', message: 'Compare Tuesday.' });
        publish('delta', { text: 'Steered part and ' });
        await expect(page.getByText('Compare Tuesday.', { exact: true })).toBeVisible();
        await expect(page.getByText('Steered part and', { exact: true })).toBeVisible();
      }
      const closedBeforeInterruption = closedReaders;
      if (interruption === 'network pause') {
        await context.setOffline(true);
        // Offline emulation can leave an open stream running, so close it at the server.
        for (const reader of readers) reader.destroy();
        complete();
        await context.setOffline(false);
        await page.evaluate(() => window.dispatchEvent(new Event('online')));
      } else if (interruption === 'tab switch') {
        const dialogs: string[] = [];
        page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.accept().catch(() => {}); });
        await page.getByRole('button', { name: '1. Dates', exact: true }).click();
        await expect(page).toHaveURL(/\/dates$/);
        expect(dialogs).toEqual([]);
        complete();
        await page.getByRole('button', { name: '12. Experimental AI', exact: true }).click();
      } else {
        await page.reload();
        complete();
      }
      await expect.poll(() => closedReaders).toBeGreaterThan(closedBeforeInterruption);
      await expect(page.getByText(`${steered ? 'Steered' : 'First'} part and complete answer.`, { exact: true })).toBeVisible();
      if (steered) {
        await expect(page.getByText('First part and', { exact: true })).toHaveCount(1);
        await expect(page.getByText('Compare Tuesday.', { exact: true })).toHaveCount(1);
      }
      await expect(page.getByText('Continue while disconnected', { exact: true })).toHaveCount(1);
      await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0);
      expect(executions).toBe(1);
      expect(unauthorized).toBe(0);
      expect(new Set(messageIds).size).toBe(1);
      // The reconnecting reader continued from its saved cursor instead of replaying everything.
      expect(cursors.at(-1)).toBeGreaterThanOrEqual(steered ? 4 : 2);
    } finally {
      await context.setOffline(false);
      server.closeAllConnections();
      await new Promise<void>(resolve => server.close(() => resolve()));
    }
  });
}
