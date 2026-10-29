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

for (const phone of [false, true]) {
  test(`selects and forgets recent chats on ${phone ? 'a phone' : 'desktop'}`, async ({ browser }, testInfo) => {
    const context = await browser.newContext(phone
      ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
      : { viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const writes: string[] = [];
    let replayed = false;
    await page.route('**/ai/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (request.method() !== 'GET') writes.push(`${request.method()} ${path}`);
      const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      if (path.endsWith('/capabilities')) return json({
        app_version: 'test', session_retention_seconds: 2592000, model_selection: true,
        auth: { required: false },
        file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000, max_bytes_per_session: 200000000 },
      });
      if (path.endsWith('/models')) return json({ default_model: 'fast', models: [
        { id: 'fast', name: 'Fast', default_reasoning: 'default', reasoning_options: [{ id: 'default', label: 'Default' }] },
        { id: 'deep', name: 'Deep', default_reasoning: 'high', reasoning_options: [{ id: 'high', label: 'High' }] },
      ] });
      if (path.endsWith('/model-selection')) {
        if (request.method() === 'PUT') return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Model is fixed' }) });
        return json({ model: 'fast', reasoning: 'default', locked: true });
      }
      if (path.endsWith('/uploads')) return json([]);
      if (path.endsWith('/events')) {
        if (replayed) return route.fulfill({ contentType: 'text/event-stream', body: ': heartbeat\n\n' });
        replayed = true;
        const events = [
          ['run_start', { trigger: 'optimization' }],
          ['schedule_applied', { schedule_yaml: 'description: Changed while away\n', diff: 'Changes from earlier work', replaced_queued_schedule: false }],
          ['done', {}],
        ];
        return route.fulfill({ contentType: 'text/event-stream', body: events.map(([type, data], index) =>
          `id: ${index + 6}\nevent: ${type}\ndata: ${JSON.stringify({ ...data as object, run_id: 'away-run' })}\n\n`).join('') });
      }
      if (/\/sessions\/[^/]+$/.test(path)) return json({ expires_in_seconds: 2592000 });
      return route.fulfill({ status: 404 });
    });
    const baseURL = testInfo.project.use.baseURL!;
    await page.goto(baseURL);
    await page.evaluate(() => {
      const now = Date.now();
      localStorage.setItem('nurse-scheduling-ai-server', '/ai');
      localStorage.setItem('nurse-scheduling-ai-history', JSON.stringify({ appVersion: 'test', entries: ['Ward A', 'Ward B'].map((ward, index) => ({
        lastActivityAt: now - index * 60000,
        conversation: {
          sessionId: `session-${index}`, endpoint: '/ai', lastActivityAt: now - index * 60000,
          expiresAt: now + 2592000000, retentionSeconds: 2592000, sessionEventId: 5,
          syncedSchedule: `description: ${ward}\n`,
          messages: [{ id: 'question', role: 'user', content: `Review ${ward}` },
            { id: 'answer', role: 'assistant', content: `Earlier answer for ${ward}.`, activity: [{ kind: 'response', text: `Earlier answer for ${ward}.` }] }],
        },
      })) }));
    });
    await page.goto(`${baseURL}/experimental-ai`);
    await expect(page.getByLabel('AI model')).toBeEnabled();
    await page.getByLabel('AI model').selectOption('deep');
    const history = page.getByRole('complementary', { name: 'Recent chats' });
    if (phone) await history.getByRole('button', { name: 'Recent chats (2)' }).click();
    await history.getByRole('button', { name: /^Review Ward A/ }).click();
    await expect(page.getByLabel('AI model')).toHaveValue('fast');
    await expect(page.getByLabel('AI model')).toBeDisabled();
    await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Continue this chat.');
    await expect(page.getByRole('button', { name: 'Send' })).toBeEnabled();
    await page.getByRole('textbox', { name: 'Ask about the current schedule' }).clear();
    await expect(page.getByText('Earlier answer for Ward A.')).toBeVisible();
    await expect.poll(() => page.evaluate(() => (
      JSON.parse(localStorage.getItem('nurse-scheduling-ai-history')!).appVersion
    ))).toBe(process.env.APP_VERSION_OVERRIDE);
    await expect(page.getByLabel('Schedule data status')).toContainText('differs');
    await expect(page.getByText(/Browser schedule data was kept unchanged/)).toBeVisible();
    await expect(page.getByText('Saved in this chat')).toBeVisible();
    await expect(page.getByRole('complementary', { name: 'Session files' })).toBeVisible();
    expect(writes).toEqual([]);
    await expect(history.getByRole('button', { name: /^Review Ward A/ })).toHaveAttribute('aria-current', 'true');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    expect(overflow).toBe(false);
    if (phone) {
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.setViewportSize({ width: 390, height });
    }
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: `../artifacts/session-history-${phone ? 'phone' : 'desktop'}.png` });
    if (phone) await page.setViewportSize({ width: 390, height: 844 });
    await context.storageState({ path: `../artifacts/session-history-${phone ? 'phone' : 'desktop'}-storage.json` });
    await history.getByRole('button', { name: 'Remove chat: Review Ward A' }).click();
    await expect(history.getByRole('button', { name: /^Review Ward A/ })).toHaveCount(0);
    await expect(page.getByText('Earlier answer for Ward A.')).toBeVisible();
    page.on('dialog', dialog => dialog.accept());
    await history.getByRole('button', { name: 'Clear history' }).click();
    await expect(history.getByText('No recent chats.')).toBeVisible();
    expect(writes).toEqual([]);
    await page.reload();
    if (phone) await history.getByRole('button', { name: 'Recent chats (0)' }).click();
    await expect(history.getByText('No recent chats.')).toBeVisible();
    await expect(page.getByText('Earlier answer for Ward A.')).toHaveCount(0);
    await context.close();
  });
}
