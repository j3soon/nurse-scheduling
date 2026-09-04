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
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';

interface CapturedRequests {
  scheduleYaml: string;
  messageBody: string;
  messageBodies: string[];
  messageContentType: string;
  authorizationHeaders: string[];
}

async function startCancelableAiBackend() {
  let disconnected = false;
  const server = createServer((request, response) => {
    request.resume();
    const headers = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Origin': request.headers.origin ?? '*',
    };
    if (request.method === 'OPTIONS') {
      response.writeHead(204, headers).end();
      return;
    }
    if (request.url === '/ai/capabilities') {
      response.writeHead(200, { ...headers, 'Content-Type': 'application/json' }).end(JSON.stringify({
        image_attachments: {
          enabled: false,
          accepted_media_types: ['image/png'],
          max_files: 1,
          max_bytes_per_file: 1000,
        },
        document_attachments: {
          enabled: false,
          accepted_extensions: ['.txt'],
          max_files: 1,
          max_bytes_per_file: 1000,
        },
      }));
      return;
    }
    if (request.url === '/ai/sessions') {
      response.writeHead(201, { ...headers, 'Content-Type': 'application/json' })
        .end(JSON.stringify({ id: 'cancel-session' }));
      return;
    }
    if (request.url === '/ai/sessions/cancel-session/messages') {
      response.writeHead(200, {
        ...headers,
        'Cache-Control': 'no-cache',
        'Content-Type': 'text/event-stream',
      });
      response.write('event: tool_start\ndata: {"name":"bash","arguments":"{\\"command\\":\\"sleep 30\\"}"}\n\n');
      response.on('close', () => {
        if (!response.writableEnded) disconnected = true;
      });
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
  attachments: { images: boolean; documents: boolean },
  answerDeltas = ['The image and schedule ', 'were received.'],
  failFirstMessage = false,
  requiredAuthToken?: string,
): Promise<CapturedRequests> {
  const captured = {
    scheduleYaml: '',
    messageBody: '',
    messageBodies: [] as string[],
    messageContentType: '',
    authorizationHeaders: [] as string[],
  };

  await page.route('**/ai/**', async route => {
    const request = route.request();
    const frontendOrigin = request.headers()['origin'] ?? 'http://127.0.0.1:3000';
    const corsHeaders = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Origin': frontendOrigin,
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
          image_attachments: {
            enabled: attachments.images,
            accepted_media_types: ['image/jpeg', 'image/png', 'image/webp'],
            max_files: 4,
            max_bytes_per_file: 5_000_000,
          },
          document_attachments: {
            enabled: attachments.documents,
            accepted_extensions: ['.txt', '.md', '.csv', '.pdf', '.xlsx'],
            max_files: 4,
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

    captured.messageBody = request.postData() ?? '';
    captured.messageBodies.push(captured.messageBody);
    captured.messageContentType = request.headers()['content-type'] ?? '';
    const firstMessageFailed = failFirstMessage && captured.messageBodies.length === 1;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: corsHeaders,
      body: firstMessageFailed
        ? [
          `event: tool_start\ndata: ${JSON.stringify({ name: 'bash', arguments: '{"command":"sleep 30"}' })}\n\n`,
          'event: delta\ndata: {"text":"Provisional response."}\n\n',
          'event: error\ndata: {"message":"The temporary AI sandbox failed."}\n\n',
        ].join('')
        : [
          ...answerDeltas.map(text => `event: delta\ndata: ${JSON.stringify({ text })}\n\n`),
          'event: done\ndata: {"message_id":"answer-id"}\n\n',
        ].join(''),
    });
  });

  return captured;
}

test('asks about the current schedule and renders a streamed answer', async ({ page }) => {
  const captured = await mockAiBackend(page, { images: false, documents: false });

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who works first?');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  const composerBox = await page.locator('main form').boundingBox();
  const viewport = page.viewportSize();
  expect(composerBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(Math.abs(composerBox!.y + composerBox!.height - viewport!.height)).toBeLessThanOrEqual(2);
  await expect(page.getByRole('contentinfo')).toHaveCount(0);
  expect(JSON.parse(captured.messageBody)).toEqual({ message: 'Who works first?' });
  expect(captured.scheduleYaml).toContain('apiVersion:');

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

test('authenticates AI session requests with an explicitly remembered token', async ({ page }) => {
  const authToken = 'browser-ai-auth-token';
  const captured = await mockAiBackend(
    page,
    { images: false, documents: false },
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
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('Authenticated response.')).toBeVisible();
  expect(captured.authorizationHeaders).toEqual([
    `Bearer ${authToken}`,
    `Bearer ${authToken}`,
  ]);
  expect(await page.evaluate(() => localStorage.getItem('nurse-scheduling-ai-auth'))).toBe(
    JSON.stringify({ endpoint: '/ai', token: authToken }),
  );
});

test('retries a failed text turn without hiding its provisional activity', async ({ page }) => {
  const captured = await mockAiBackend(
    page,
    { images: false, documents: false },
    ['Recovered response.'],
    true,
  );

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who works first?');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('Provisional response.')).toBeVisible();
  await expect(page.getByText('This turn failed and was not saved to AI history.')).toBeVisible();
  await page.getByText('bash · interrupted').click();
  await expect(page.getByText('{"command":"sleep 30"}', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry' }).click();

  await expect(page.getByText('Recovered response.')).toBeVisible();
  expect(captured.messageBodies.map(body => JSON.parse(body))).toEqual([
    { message: 'Who works first?' },
    { message: 'Who works first?' },
  ]);
});

test('Stop aborts the active AI stream', async ({ page }) => {
  const backend = await startCancelableAiBackend();
  await page.route('**/ai/**', route => {
    const requestUrl = new URL(route.request().url());
    return route.continue({ url: `${backend.origin}${requestUrl.pathname}${requestUrl.search}` });
  });

  try {
    await page.goto('/experimental-ai');
    await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Wait for this command.');
    await page.getByRole('button', { name: 'Send' }).click();

    await expect(page.getByText('bash · running')).toBeVisible();
    await page.getByRole('button', { name: 'Stop' }).click();

    await expect.poll(backend.wasDisconnected).toBe(true);
    await expect(page.getByText('bash · interrupted')).toBeVisible();
    await expect(page.getByText('This turn failed and was not saved to AI history.')).toBeVisible();
  } finally {
    await backend.close();
  }
});

test('renders assistant Markdown with safe images and copyable code', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await mockAiBackend(
    page,
    { images: false, documents: false },
    [
      '## Coverage\n\n**Alice** works Monday.\n\n',
      '| Person | Shift |\n| --- | --- |\n| Alice | D |\n\n```yaml\npeople: []\n```\n\n![tracker](https://tracker.example/pixel.png)',
    ],
  );

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Summarize coverage.');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByRole('heading', { level: 2, name: 'Coverage' })).toBeVisible();
  await expect(page.getByRole('table')).toContainText('Alice');
  await expect(page.getByText('[Remote image omitted: tracker]')).toBeVisible();
  await expect(page.locator('article img')).toHaveCount(0);

  const codeBlock = page.locator('article pre');
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
  await mockAiBackend(page, { images: false, documents: false }, [longAnswer]);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Give detailed coverage.');
  await page.getByRole('button', { name: 'Send' }).click();

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
      const buttonBox = await scrollButton.boundingBox();
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

test('previews and sends an enabled image attachment', async ({ page }) => {
  const captured = await mockAiBackend(page, { images: true, documents: false });
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );

  await page.goto('/experimental-ai');
  await page.getByLabel('Attach files').setInputFiles({ name: 'ward.png', mimeType: 'image/png', buffer: png });
  await expect(page.getByAltText('Preview of ward.png')).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('What is shown?');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  await expect(page.getByText('Attached: ward.png')).toBeVisible();
  expect(captured.messageContentType).toContain('multipart/form-data');
  expect(captured.messageBody).toContain('What is shown?');
  expect(captured.messageBody).toContain('ward.png');
});

test('previews and sends enabled document attachments', async ({ page }) => {
  const captured = await mockAiBackend(page, { images: false, documents: true });

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
      name: 'coverage.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('xlsx test'),
    },
  ]);
  await expect(page.getByText('csv', { exact: true })).toBeVisible();
  await expect(page.getByText('pdf', { exact: true })).toBeVisible();
  await expect(page.getByText('xlsx', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Check the documents.');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  await expect(page.getByText('Attached: staff.csv, notes.pdf, coverage.xlsx')).toBeVisible();
  expect(captured.messageContentType).toContain('multipart/form-data');
  expect(captured.messageBody).toContain('name="documents"');
  expect(captured.messageBody).toContain('staff.csv');
  expect(captured.messageBody).toContain('notes.pdf');
  expect(captured.messageBody).toContain('coverage.xlsx');
  expect(captured.messageBody).toContain('Alice,day');
});
