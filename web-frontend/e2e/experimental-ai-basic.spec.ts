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

import { expect, test } from '@playwright/test';

test('asks about the current schedule and renders a streamed answer', async ({ page }) => {
  let sessionBody: { schedule_yaml?: string } = {};
  let messageBody: { message?: string } = {};

  await page.route('http://127.0.0.1:8001/**', async route => {
    const request = route.request();
    const frontendOrigin = request.headers()['origin'] ?? 'http://127.0.0.1:3000';
    const corsHeaders = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Origin': frontendOrigin,
    };
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (request.url().endsWith('/sessions')) {
      sessionBody = request.postDataJSON() as typeof sessionBody;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ id: 'browser-session' }),
      });
      return;
    }

    messageBody = request.postDataJSON() as typeof messageBody;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: corsHeaders,
      body: [
        'event: delta\ndata: {"text":"Alice works "}\n\n',
        'event: delta\ndata: {"text":"the first date."}\n\n',
        'event: done\ndata: {"message_id":"answer-id"}\n\n',
      ].join(''),
    });
  });

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who works first?');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('Alice works the first date.')).toBeVisible();
  expect(messageBody.message).toBe('Who works first?');
  expect(sessionBody.schedule_yaml).toContain('apiVersion:');
});
