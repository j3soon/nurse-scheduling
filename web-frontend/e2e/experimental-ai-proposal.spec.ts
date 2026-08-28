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

const PROPOSED_YAML = `apiVersion: alpha
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

async function mockProposingBackend(page: Page): Promise<{ approvals: number; refreshed: string[] }> {
  const state = { approvals: 0, refreshed: [] as string[] };

  await page.route('**/ai/**', async route => {
    const request = route.request();
    const corsHeaders = {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
      'Access-Control-Allow-Origin': request.headers()['origin'] ?? 'http://127.0.0.1:3000',
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
          image_attachments: { enabled: false, accepted_media_types: [], max_files: 4, max_bytes_per_file: 1 },
          document_attachments: { enabled: false, accepted_extensions: [], max_files: 4, max_bytes_per_file: 1 },
        }),
      });
      return;
    }
    if (request.url().endsWith('/sessions')) {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ id: 'browser-session' }),
      });
      return;
    }
    if (request.url().endsWith('/schedule')) {
      state.refreshed.push((request.postDataJSON() as { schedule_yaml: string }).schedule_yaml);
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }
    if (request.url().endsWith('/proposal/approve')) {
      state.approvals += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: corsHeaders,
        body: JSON.stringify({ schedule_yaml: PROPOSED_YAML }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: corsHeaders,
      body: [
        'event: tool\ndata: {"name":"edit_schedule"}\n\n',
        'event: delta\ndata: {"text":"I propose adding one nurse."}\n\n',
        'event: proposal\ndata: {"diff":"- people.items[0]: added {\\"id\\": \\"Proposed Nurse\\"}"}\n\n',
        'event: done\ndata: {"message_id":"answer-id"}\n\n',
      ].join(''),
    });
  });

  return state;
}

test('approves a proposed schedule and applies it as one undoable step', async ({ page }) => {
  const state = await mockProposingBackend(page);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send' }).click();

  const proposal = page.getByRole('region', { name: 'Proposed schedule change' });
  await expect(proposal).toBeVisible();
  await expect(proposal).toContainText('added');
  await expect(page.getByText('Used schedule.yaml: edit_schedule')).toBeVisible();

  await page.getByRole('button', { name: 'Approve' }).click();

  await expect(page.getByText('The proposed schedule was applied. Undo reverts it in one step.')).toBeVisible();
  await expect(proposal).toBeHidden();
  expect(state.approvals).toBe(1);

  await page.goto('/people');
  await expect(page.getByText('1. Proposed Nurse')).toBeVisible();

  await page.keyboard.press('Control+z');
  await expect(page.getByText('1. Proposed Nurse')).toBeHidden();
});

test('keeps the schedule when a proposal is rejected', async ({ page }) => {
  await mockProposingBackend(page);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send' }).click();
  await page.getByRole('button', { name: 'Reject' }).click();

  await expect(page.getByRole('region', { name: 'Proposed schedule change' })).toBeHidden();

  await page.goto('/people');
  await expect(page.getByText('1. Proposed Nurse')).toBeHidden();
});

test('sends the applied schedule to the session before the next question', async ({ page }) => {
  const state = await mockProposingBackend(page);

  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Add a nurse.');
  await page.getByRole('button', { name: 'Send' }).click();
  await page.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByText('The proposed schedule was applied.')).toBeVisible();

  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Who is on shift?');
  await page.getByRole('button', { name: 'Send' }).click();

  // The approved schedule replaced the one the session was created with.
  await expect.poll(() => state.refreshed.length).toBe(1);
  expect(state.refreshed[0]).toContain('Proposed Nurse');
});
