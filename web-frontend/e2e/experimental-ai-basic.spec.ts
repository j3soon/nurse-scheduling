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

interface CapturedRequests {
  scheduleYaml: string;
  messageBody: string;
  messageContentType: string;
}

async function mockAiBackend(
  page: Page,
  attachments: { images: boolean; documents: boolean },
): Promise<CapturedRequests> {
  const captured = { scheduleYaml: '', messageBody: '', messageContentType: '' };

  await page.route('**/ai/**', async route => {
    const request = route.request();
    const frontendOrigin = request.headers()['origin'] ?? 'http://127.0.0.1:3000';
    const corsHeaders = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type',
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
          image_attachments: {
            enabled: attachments.images,
            accepted_media_types: ['image/jpeg', 'image/png', 'image/webp'],
            max_files: 4,
            max_bytes_per_file: 5_000_000,
          },
          document_attachments: {
            enabled: attachments.documents,
            accepted_extensions: ['.txt', '.md', '.csv'],
            max_files: 4,
            max_bytes_per_file: 50_000,
          },
        }),
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
    captured.messageContentType = request.headers()['content-type'] ?? '';
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: corsHeaders,
      body: [
        'event: delta\ndata: {"text":"The image and schedule "}\n\n',
        'event: delta\ndata: {"text":"were received."}\n\n',
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
  expect(JSON.parse(captured.messageBody)).toEqual({ message: 'Who works first?' });
  expect(captured.scheduleYaml).toContain('apiVersion:');
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

test('previews and sends an enabled CSV attachment', async ({ page }) => {
  const captured = await mockAiBackend(page, { images: false, documents: true });

  await page.goto('/experimental-ai');
  await page.getByLabel('Attach files').setInputFiles({
    name: 'staff.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('name,shift\nAlice,day\n'),
  });
  await expect(page.getByText('csv', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Check the CSV.');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('The image and schedule were received.')).toBeVisible();
  await expect(page.getByText('Attached: staff.csv')).toBeVisible();
  expect(captured.messageContentType).toContain('multipart/form-data');
  expect(captured.messageBody).toContain('name="documents"');
  expect(captured.messageBody).toContain('staff.csv');
  expect(captured.messageBody).toContain('Alice,day');
});
