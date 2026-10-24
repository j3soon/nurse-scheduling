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

const APPLIED_YAML = `apiVersion: alpha
description: ''
dates:
  range:
    startDate: '2026-01-01'
    endDate: '2026-01-02'
  items: []
  groups: []
people:
  items:
  - id: Proposed Nurse
    description: ''
    history: []
  groups: []
shiftTypes:
  items: []
  groups: []
preferences: []
`;
const CHECK = 'Trusted schedule check after this command:\nThe candidate passed trusted server-side validation.';

async function mockChangingBackend(page: Page, holdAnswer = false, retryNotice = false) {
  const state = { sessionSchedule: '', refreshed: [] as string[], finishAnswer: () => {}, messages: 0, stops: 0 };
  const baseURL = test.info().project.use.baseURL;
  if (!baseURL) throw new Error('Playwright baseURL is required for the AI backend mock.');
  const allowedOrigin = new URL(baseURL).origin;
  const journal: string[] = [];
  const accepted = new Map<string, string>();
  let wakeReader: (() => void) | undefined;
  const wake = () => {
    wakeReader?.();
    wakeReader = undefined;
  };

  await page.route('**/ai/**', async route => {
    const request = route.request();
    const corsHeaders = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type, Last-Event-ID',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
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
          file_attachments: { enabled: true, max_files: 8, max_bytes_per_file: 5_000_000, max_bytes_per_session: 200_000_000 },
        }),
      });
      return;
    }
    if (request.url().endsWith('/sessions')) {
      state.sessionSchedule = (request.postDataJSON() as { schedule_yaml: string }).schedule_yaml;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ id: 'browser-session' }),
      });
      return;
    }
    if (new URL(request.url()).pathname.endsWith('/events')) {
      const cursor = Number(request.headers()['last-event-id'] ?? 0);
      if (journal.length <= cursor) await new Promise<void>(resolve => { wakeReader = resolve; });
      await route.fulfill({ status: 200, contentType: 'text/event-stream', headers: corsHeaders, body: journal.slice(cursor).join('') });
      return;
    }
    if (request.method() === 'GET' && request.url().endsWith('/browser-session')) {
      await route.fulfill({ status: 200, contentType: 'application/json', headers: corsHeaders,
        body: JSON.stringify({ expires_in_seconds: 3600 }) });
      return;
    }
    if (request.url().endsWith('/stop')) {
      state.stops++;
      await route.fulfill({ status: 202, headers: corsHeaders });
      return;
    }
    if (request.url().endsWith('/schedule')) {
      state.sessionSchedule = (request.postDataJSON() as { schedule_yaml: string }).schedule_yaml;
      state.refreshed.push(state.sessionSchedule);
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (request.url().endsWith('/uploads')) {
      await route.fulfill({ json: [], headers: corsHeaders });
      return;
    }
    const messageId = (request.postDataJSON() as { message_id: string }).message_id;
    const previous = accepted.get(messageId);
    if (previous) {
      await route.fulfill({ status: 202, json: { run_id: previous }, headers: corsHeaders });
      return;
    }
    state.messages++;
    const runId = `answer-${journal.length}`;
    accepted.set(messageId, runId);
    const publish = (type: string, data: Record<string, unknown>) => {
      journal.push(`id: ${journal.length + 1}\nevent: ${type}\ndata: ${JSON.stringify({ ...data, run_id: runId })}\n\n`);
    };
    publish('run_start', { trigger: 'user' });
    if (retryNotice) publish('model_input', { system: 'Synthetic chat instructions', messages: [{ kind: 'question', content: 'Add a nurse.' }] });
    publish('reasoning', { text: 'The ward has one nurse, so I will add another.' });
    publish('tool', {
      name: 'bash', arguments: '{"command":"python3 /tmp/edit.py"}', result: `exit_code: 0\n\n${CHECK}`, ok: true,
      schedule_check: { ok: true, text: CHECK },
    });
    publish('schedule_change', { schedule_yaml: APPLIED_YAML });
    publish('delta', { text: 'I added one nurse.' });
    // The backend adopts the schedule when the run commits, just before it reports done.
    const finish = () => {
      publish('schedule_applied', {
        schedule_yaml: APPLIED_YAML, diff: '- people.items[0]: added {"id": "Proposed Nurse"}',
        replaced_queued_schedule: false,
      });
      state.sessionSchedule = APPLIED_YAML;
      publish('done', {});
      wake();
    };
    if (retryNotice) {
      publish('provider_retry', { message: 'The AI provider timed out. Retrying in 2 s (attempt 2 of 5).' });
      state.finishAnswer = finish;
    } else if (holdAnswer) state.finishAnswer = finish;
    else finish();
    await route.fulfill({ status: 202, contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ run_id: runId }) });
    wake();
  });

  return state;
}

test('keeps an automatic provider retry notice in the same run across reload', async ({ page }) => {
  const state = await mockChangingBackend(page, false, true);
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  const notice = page.getByText('The AI provider timed out. Retrying in 2 s (attempt 2 of 5).');
  await expect(notice).toBeVisible();
  await page.reload();
  await expect(notice).toBeVisible();
  await expect(page.getByRole('button', { name: /retry/i })).toHaveCount(0);
  state.finishAnswer();
  await expect(page.getByText('Applied to your schedule')).toBeVisible();
  expect(state.messages).toBe(1);
  await page.goto('/people');
  await expect(page.getByText('1. Proposed Nurse')).toBeVisible();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('1. Proposed Nurse')).toBeHidden();
});

test('applies the schedule a response finishes with as one undoable step', async ({ page }) => {
  await mockChangingBackend(page);

  await page.goto('/experimental-ai');
  await expect(page.getByText('Press Ctrl+Z to undo them.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  await expect(page.getByText('Applied to your schedule')).toBeVisible();
  await page.getByText('Schedule check passed').click();
  await expect(page.getByText('The candidate passed trusted server-side validation.').last()).toBeVisible();
  await expect(page.getByText('schedule edit')).toBeVisible();
  await page.getByText('bash', { exact: true }).click();
  await expect(page.getByRole('region', { name: 'Tool arguments' }).getByRole('heading', { name: 'Command' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Tool result' }).getByRole('heading', { name: 'Result' })).toBeVisible();
  await page.getByLabel('Chat messages').screenshot({ path: '../artifacts/tool-command-result.png' });
  await expect(page.getByRole('button', { name: 'Approve' })).toBeHidden();

  await page.goto('/people');
  await expect(page.getByText('1. Proposed Nurse')).toBeVisible();

  await page.keyboard.press('Control+z');
  await expect(page.getByText('1. Proposed Nurse')).toBeHidden();
});

test('applies the schedule only when the response finishes', async ({ page }) => {
  const state = await mockChangingBackend(page, true);
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('schedule edit')).toBeVisible();
  await expect(page.getByText('Applied to your schedule')).toBeHidden();

  state.finishAnswer();

  await expect(page.getByText('Applied to your schedule')).toBeVisible();
  await page.goto('/people');
  await expect(page.getByText('1. Proposed Nurse')).toBeVisible();
});

test('sends the applied schedule to the session before the next question', async ({ page }) => {
  const state = await mockChangingBackend(page);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('Applied to your schedule')).toBeVisible();

  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who is on shift?');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  // The browser regenerates the applied schedule in its own format before the next question.
  await expect.poll(() => state.refreshed.length).toBe(1);
  expect(state.refreshed[0]).toContain('Proposed Nurse');
});

test('overwrites browser Undo with a notice and preserves a later Undo across replay and reload', async ({ page }) => {
  const state = await mockChangingBackend(page, true);
  await page.goto('/people');
  await page.getByRole('button', { name: 'Add Person', exact: true }).click();
  await page.getByPlaceholder('Enter person ID').fill('Before response');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('1. Before response')).toBeVisible();

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('schedule edit')).toBeVisible();
  await page.keyboard.press('Control+z');
  state.finishAnswer();
  await expect(page.getByText(/replaced changes made during this response/)).toBeVisible();
  await page.screenshot({ path: '../artifacts/fix-branch-review/overwrite-notice.png', fullPage: true });

  await page.keyboard.press('Control+z');
  await expect.poll(() => page.evaluate(() => {
    const saved = JSON.parse(sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    return { receipt: saved.appliedScheduleRuns?.['answer-0'], pending: saved.pendingRequest };
  })).toEqual({ receipt: expect.any(String), pending: null });
  // Request older output again to verify that run identity, rather than its cursor or YAML hash,
  // prevents a completed result from replacing the schedule restored by Undo.
  await page.evaluate(() => {
    const key = 'nurse-scheduling-ai-conversation';
    const saved = JSON.parse(sessionStorage.getItem(key)!);
    saved.sessionEventId = 0;
    sessionStorage.setItem(key, JSON.stringify(saved));
  });
  await page.reload();
  await expect(page.getByText('Applied to your schedule')).toBeVisible();
  await page.goto('/people');
  await expect(page.getByText('1. Proposed Nurse')).toBeHidden();
  await expect(page.getByText('1. Before response')).toBeHidden();
  expect(state.messages).toBe(1);
  expect(state.stops).toBe(0);
  expect(state.refreshed).toEqual([]);
});

test('keeps reasoning and tool detail out of the way until asked for', async ({ page }) => {
  await mockChangingBackend(page);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();

  const reasoning = page.getByText('The ward has one nurse, so I will add another.');
  await expect(page.getByText(/^Reasoning ·/)).toBeVisible();
  await expect(reasoning).toBeHidden();

  await page.getByText(/^Reasoning ·/).click();
  await expect(reasoning).toBeVisible();

  await page.getByText('bash', { exact: true }).click();
  await expect(page.getByText(/^exit_code: 0/)).toBeVisible();

  // Turning the categories off hides them for good, across reloads.
  await page.getByRole('checkbox', { name: 'Show reasoning' }).uncheck();
  await page.getByRole('checkbox', { name: 'Show tool activity' }).uncheck();
  await expect(page.getByText(/^Reasoning ·/)).toBeHidden();
  await expect(page.getByText('Schedule check passed')).toBeVisible();
  // The applied change stays visible, because it changed the user's schedule.
  await expect(page.getByText('Applied to your schedule')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Show reasoning' })).not.toBeChecked();
});
