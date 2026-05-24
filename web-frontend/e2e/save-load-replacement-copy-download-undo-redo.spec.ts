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

import { expect, test } from './test';
import { disableModalDialogs, seedSchedulingState } from './helpers';

async function readDownloadText(download: Awaited<ReturnType<typeof Promise.resolve>>) {
  const stream = await (download as { createReadStream: () => Promise<NodeJS.ReadableStream | null> }).createReadStream();
  let text = '';
  if (stream) {
    for await (const chunk of stream) {
      text += chunk.toString();
    }
  }
  return text;
}

test('save-load preview, copy, and download follow undo and redo of an uploaded replacement', async ({ page, context }) => {
  /*
   * Steps:
   * 1. Seed an original schedule and upload a replacement YAML over it.
   * 2. Undo the upload and confirm preview, copy, and download all reflect the original state.
   * 3. Redo the upload and confirm preview, copy, and download all reflect the replacement state.
   */
  await disableModalDialogs(page);
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);

  await seedSchedulingState(page, {
    apiVersion: 'test',
    description: 'original save-load export state',
    dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
    people: {
      items: [{ id: 'P1', description: 'Original nurse', history: [] }],
      groups: [{ id: 'Team Alpha', members: ['P1'], description: 'Original team' }],
      history: [],
    },
    shiftTypes: { items: [{ id: 'D', description: 'Original shift' }], groups: [] },
    preferences: [{ type: 'at most one shift per day' }],
    export: { formatting: [] },
  });

  const replacementYaml = `apiVersion: test\ndescription: replacement export state\ndates:\n  range:\n    startDate: 2026-06-01\n    endDate: 2026-06-01\n  groups: []\npeople:\n  items:\n    - id: P9\n      description: Replacement nurse\n      history: []\n  groups:\n    - id: Team Beta\n      members: [P9]\n      description: Replacement team\n  history: []\nshiftTypes:\n  items:\n    - id: ZX\n      description: Replacement shift\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'replacement-export.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(replacementYaml, 'utf8'),
  });

  await page.getByRole('heading', { name: 'Save and Load', exact: true }).click();
  await page.keyboard.press('Control+z');
  await expect(page.locator('pre')).toContainText('Team Alpha');
  await expect(page.locator('pre')).not.toContainText('Team Beta');

  await page.getByRole('button', { name: 'Copy' }).click();
  await expect(page.getByRole('button', { name: 'Copied!' })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => navigator.clipboard.readText())).toContain('Team Alpha');

  const undoDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const undoDownload = await undoDownloadPromise;
  await expect(await readDownloadText(undoDownload)).toContain('Team Alpha');

  await page.getByRole('heading', { name: 'Save and Load', exact: true }).click();
  await page.keyboard.press('Control+y');
  await expect(page.locator('pre')).toContainText('Team Beta');
  await expect(page.locator('pre')).not.toContainText('Team Alpha');

  await page.getByRole('button', { name: 'Copy' }).click();
  await expect(page.getByRole('button', { name: 'Copied!' })).toBeVisible();
  await expect.poll(async () => page.evaluate(() => navigator.clipboard.readText())).toContain('Team Beta');

  const redoDownloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const redoDownload = await redoDownloadPromise;
  await expect(await readDownloadText(redoDownload)).toContain('Team Beta');
});
