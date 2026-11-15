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

import { expect, test, type Page } from '@playwright/test';

const historyKey = 'nurse-scheduling-ai-history';
const tabKey = 'nurse-scheduling-ai-conversation';

declare global {
  interface Window {
    releaseHistoryTestLock?: () => void;
    heldHistoryTestLock?: Promise<unknown>;
  }
}

async function mockHistoryBackend(page: Page, sessionId: string, failFirstCreation = false) {
  const journal: string[] = [];
  let wake: (() => void) | undefined;
  let turns = 0;
  let creations = 0;
  let scheduleSpecYaml = '';
  await page.route('**/ai/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path.endsWith('/capabilities')) return json({
      app_version: 'v0.0.0', auth: { required: false }, session_retention_seconds: 172800,
      file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000, max_bytes_per_session: 200000000 },
    });
    if (path.endsWith('/v1/sessions')) {
      if (failFirstCreation) {
        failFirstCreation = false;
        return json({ detail: 'Temporary session creation failure' }, 503);
      }
      scheduleSpecYaml = request.postDataJSON().schedule_spec_yaml;
      turns = 0;
      journal.length = 0;
      const id = creations++ === 0 ? sessionId : `${sessionId}-${creations}`;
      return json({ id }, 201);
    }
    if (path.endsWith('/events')) {
      const cursor = Number(request.headers()['last-event-id'] ?? 0);
      if (journal.length <= cursor) await new Promise<void>(resolve => { wake = resolve; });
      return route.fulfill({ contentType: 'text/event-stream', body: journal.slice(cursor).join('') });
    }
    if (path.endsWith('/messages')) {
      const runId = `run-${++turns}`;
      const question = request.postDataJSON().message;
      for (const [kind, data] of [
        ['run_start', { trigger: 'user' }],
        ['model_input', { system: 'History test', schedule_spec_yaml: scheduleSpecYaml, messages: [{ kind: 'question', content: question }] }],
        ['delta', { text: `Answer ${turns}.` }],
        ['done', {}],
      ] as const) {
        journal.push(`id: ${journal.length + 1}\nevent: ${kind}\ndata: ${JSON.stringify({ ...data, run_id: runId })}\n\n`);
      }
      wake?.();
      wake = undefined;
      return json({ run_id: runId }, 202);
    }
    if (path.endsWith('/uploads')) return json([]);
    if (path.endsWith('/schedule-spec')) return json({});
    if (/\/v1\/sessions\/[^/]+$/.test(path)) return json({ expires_in_seconds: 172800 });
    return json({}, 404);
  });
  return () => turns;
}

async function openChat(page: Page, sessionId: string, failFirstCreation = false) {
  const countTurns = await mockHistoryBackend(page, sessionId, failFirstCreation);
  await page.goto('/experimental-ai');
  await expect(page.getByRole('group', { name: 'AI versions' })).toContainText('Backend v0.0.0');
  return countTurns;
}

async function ask(page: Page, question: string, answer = 'Answer 1.') {
  await page.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }).fill(question);
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Chat messages' }).getByText(answer, { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeHidden();
}

async function holdLock(page: Page) {
  await page.evaluate(async key => {
    let acquired!: () => void;
    const ready = new Promise<void>(resolve => { acquired = resolve; });
    window.heldHistoryTestLock = navigator.locks.request(key, () => {
      acquired();
      return new Promise<void>(resolve => { window.releaseHistoryTestLock = resolve; });
    });
    await ready;
  }, historyKey);
}

async function releaseLock(page: Page) {
  await page.evaluate(async () => { window.releaseHistoryTestLock?.(); await window.heldHistoryTestLock; });
}

const storedIds = (page: Page) => page.evaluate(key => (
  JSON.parse(localStorage.getItem(key) ?? '{"entries":[]}').entries.map((entry: { conversation: { sessionId: string } }) => entry.conversation.sessionId).sort()
), historyKey);

const tabSnapshot = (page: Page) => page.evaluate(key => JSON.parse(sessionStorage.getItem(key) ?? 'null'), tabKey);

test('serializes two first saves and cleanup under a real browser lock', async ({ page, context }) => {
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  const second = await context.newPage();
  await openChat(page, 'first');
  await openChat(second, 'second');
  await ask(page, 'First chat');
  await ask(second, 'Second chat');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  await expect.poll(async () => (await tabSnapshot(second))?.historyPending).toBe(true);
  expect(await storedIds(page)).toEqual([]);
  await releaseLock(holder);
  await expect.poll(() => storedIds(page)).toEqual(['first', 'second']);
  for (const tab of [page, second]) {
    await expect.poll(async () => (await tabSnapshot(tab))?.historyPending).toBe(false);
    const history = tab.getByRole('complementary', { name: 'Recent chats' });
    await expect(history.getByRole('button', { name: /^First chat/ })).toBeVisible();
    await expect(history.getByRole('button', { name: /^Second chat/ })).toBeVisible();
  }
});

test('recovers the latest tab snapshot when reloading while its first save waits', async ({ page, context }) => {
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  const countTurns = await openChat(page, 'restored');
  await ask(page, 'Recover while waiting');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  await page.reload();
  await expect(page.getByRole('region', { name: 'Chat messages' }).getByText('Answer 1.', { exact: true })).toBeVisible();
  expect(await storedIds(page)).toEqual([]);
  await releaseLock(holder);
  await expect.poll(() => storedIds(page)).toEqual(['restored']);
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(false);
  expect(countTurns()).toBe(1);
});

test('finishes waiting saves when the tab holding the lock closes', async ({ page, context }) => {
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  await openChat(page, 'released');
  await ask(page, 'Save after holder closes');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  expect(await storedIds(page)).toEqual([]);
  await holder.close();
  await expect.poll(() => storedIds(page)).toEqual(['released']);
});

test('keeps a chat forgotten when navigation overlaps its first save and another tab clears history', async ({ page, context }) => {
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  const countTurns = await openChat(page, 'remounted');
  await ask(page, 'Keep creation permission through navigation');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect(page).toHaveURL(/\/dates$/);
  const clearer = await context.newPage();
  await clearer.goto('/');
  await clearer.evaluate(key => {
    window.heldHistoryTestLock = navigator.locks.request(key, () => localStorage.removeItem(key));
  }, historyKey);
  await page.getByRole('button', { name: '12. Experimental AI' }).click();
  await expect(page.getByRole('region', { name: 'Chat messages' }).getByText('Answer 1.', { exact: true })).toBeVisible();
  await releaseLock(holder);
  await clearer.evaluate(async () => { await window.heldHistoryTestLock; });
  await expect.poll(() => tabSnapshot(page)).toBeNull();
  expect(await storedIds(page)).toEqual([]);
  expect(countTurns()).toBe(1);
});

test('removing an open chat cancels waiting updates and prevents later saves', async ({ page, context }) => {
  await openChat(page, 'removed');
  await ask(page, 'Remove this chat');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(false);
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  await ask(page, 'Update waiting for the lock', 'Answer 2.');
  const history = page.getByRole('complementary', { name: 'Recent chats' });
  await history.getByRole('button', { name: 'Remove chat: Remove this chat' }).click();
  expect(await storedIds(page)).toEqual(['removed']);
  await releaseLock(holder);
  await expect.poll(() => storedIds(page)).toEqual([]);
  await expect.poll(() => tabSnapshot(page)).toBeNull();
  await ask(page, 'Continue the forgotten chat', 'Answer 3.');
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  expect(await storedIds(page)).toEqual([]);
  expect(await tabSnapshot(page)).toBeNull();
});

test('clearing history cancels a waiting first save and keeps it forgotten', async ({ page, context }) => {
  await openChat(page, 'first');
  await ask(page, 'Older chat');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(false);
  await page.getByRole('complementary', { name: 'Recent chats' }).getByRole('button', { name: 'New chat' }).click();
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  await ask(page, 'Pending first save');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  page.on('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Clear history', exact: true }).click();
  await releaseLock(holder);
  await expect.poll(() => storedIds(page)).toEqual([]);
  await expect.poll(() => tabSnapshot(page)).toBeNull();
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  expect(await storedIds(page)).toEqual([]);
  expect(await tabSnapshot(page)).toBeNull();
});

test('keeps earlier pending chats excluded after another tab clears and the pending tab reloads', async ({ page, context }) => {
  const clearer = await context.newPage();
  await openChat(clearer, 'older');
  await ask(clearer, 'Older chat');
  await expect.poll(async () => (await tabSnapshot(clearer))?.historyPending).toBe(false);
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  const countTurns = await openChat(page, 'pending');
  await ask(page, 'Must stay excluded after Clear');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  clearer.on('dialog', dialog => dialog.accept());
  await clearer.getByRole('button', { name: 'Clear history', exact: true }).click();
  await expect.poll(() => clearer.evaluate(async key => (
    (await navigator.locks.query()).pending?.some(lock => lock.name === key)
  ), historyKey)).toBe(true);
  await page.reload();
  await expect(page.getByRole('region', { name: 'Chat messages' }).getByText('Answer 1.', { exact: true })).toBeVisible();
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  await releaseLock(holder);
  await expect.poll(() => tabSnapshot(page)).toBeNull();
  expect(await storedIds(page)).toEqual([]);
  expect(countTurns()).toBe(1);
  // The open chat remains usable but cannot enter Recent chats again.
  await ask(page, 'Continue the excluded chat', 'Answer 2.');
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  expect(await storedIds(page)).toEqual([]);
  expect(await tabSnapshot(page)).toBeNull();
  await page.getByRole('complementary', { name: 'Recent chats' }).getByRole('button', { name: 'New chat' }).click();
  await ask(page, 'New chat after Clear');
  await expect.poll(() => storedIds(page)).toEqual(['pending-2']);
  // Removing the final record and cleanup must preserve the boundary marker.
  const marker = await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).clearGeneration, historyKey);
  await page.getByRole('button', { name: 'Remove chat: New chat after Clear', exact: true }).click();
  await expect.poll(() => storedIds(page)).toEqual([]);
  await page.reload();
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).clearGeneration, historyKey)).toBe(marker);
});

test('clears matching tab recovery when Clear commits after navigating away', async ({ page, context }) => {
  await openChat(page, 'clear-away');
  await ask(page, 'Older saved chat');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(false);
  const holder = await context.newPage();
  await holder.goto('/');
  await holdLock(holder);
  await page.getByRole('complementary', { name: 'Recent chats' }).getByRole('button', { name: 'New chat' }).click();
  await ask(page, 'Pending chat to forget');
  await expect.poll(async () => (await tabSnapshot(page))?.historyPending).toBe(true);
  page.on('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Clear history', exact: true }).click();
  await page.getByRole('button', { name: '1. Dates' }).click();
  await expect(page).toHaveURL(/\/dates$/);
  await releaseLock(holder);
  await expect.poll(() => tabSnapshot(page)).toBeNull();
  expect(await storedIds(page)).toEqual([]);
  await page.getByRole('button', { name: '12. Experimental AI' }).click();
  await expect(page.getByRole('region', { name: 'Chat messages' }).getByText('Pending chat to forget', { exact: true })).toHaveCount(0);
  expect(await storedIds(page)).toEqual([]);
});

test('keeps a failed creation in its original chat boundary when retrying after Clear', async ({ page, context }) => {
  const clearer = await context.newPage();
  await openChat(clearer, 'older');
  await ask(clearer, 'Older chat');
  await expect.poll(async () => (await tabSnapshot(clearer))?.historyPending).toBe(false);
  await openChat(page, 'creation-retry', true);
  await page.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }).fill('Chat begun before Clear');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Temporary session creation failure' })).toBeVisible();
  clearer.on('dialog', dialog => dialog.accept());
  await clearer.getByRole('button', { name: 'Clear history', exact: true }).click();
  await expect.poll(() => tabSnapshot(clearer)).toBeNull();
  await ask(page, 'Retry in the same chat');
  await expect.poll(() => tabSnapshot(page)).toBeNull();
  expect(await storedIds(page)).toEqual([]);
  const history = page.getByRole('complementary', { name: 'Recent chats' });
  await expect(history.getByText('No recent chats.')).toBeVisible();
  await history.getByRole('button', { name: 'New chat' }).click();
  await ask(page, 'New chat after Clear');
  await expect.poll(() => storedIds(page)).toEqual(['creation-retry-2']);
});

test('keeps the chat and tab recovery available when browser locking is unavailable', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined }));
  await openChat(page, 'unsupported');
  await expect(page.getByText(/Recent chats cannot be saved or removed/)).toBeVisible();
  await ask(page, 'Continue without shared history');
  await expect.poll(async () => (await tabSnapshot(page))?.messages.some((message: { content: string }) => message.content === 'Answer 1.')).toBe(true);
  expect(await storedIds(page)).toEqual([]);
  await page.reload();
  await expect(page.getByRole('region', { name: 'Chat messages' }).getByText('Answer 1.', { exact: true })).toBeVisible();
  expect(await storedIds(page)).toEqual([]);
});
