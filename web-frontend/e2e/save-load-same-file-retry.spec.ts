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

test('save-load upload can retry the same filename after failure and then recover with valid YAML', async ({ page }) => {
  /*
   * Steps:
   * 1. Open Save and Load and confirm the original preview content.
   * 2. Upload one invalid YAML file and confirm the preview stays unchanged.
   * 3. Upload the same filename again with another invalid payload to confirm retry works.
   * 4. Upload the same filename with valid YAML and confirm the preview updates.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  const validYaml = `apiVersion: test\ndescription: recovered same filename\ndates:\n  range:\n    startDate: 2026-05-01\n    endDate: 2026-05-01\n  groups: []\npeople:\n  items:\n    - id: P9\n      description: Uploaded via retry\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: D\n      description: Day\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  const originalFirstLine = ((await page.locator('pre').textContent()) ?? '').split('\n')[0];
  const uploadInput = page.locator('input[type="file"]');

  await uploadInput.setInputFiles({
    name: 'schedule.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from('bad: [yaml', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0]).toContain('Error loading YAML file');
  await expect(page.locator('pre')).toContainText(originalFirstLine);

  await uploadInput.setInputFiles({
    name: 'schedule.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from('still: [bad', 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(2);
  expect(dialogs[1]).toContain('Error loading YAML file');
  await expect(page.locator('pre')).toContainText(originalFirstLine);

  await uploadInput.setInputFiles({
    name: 'schedule.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(validYaml, 'utf8'),
  });
  await expect.poll(() => dialogs.length).toBe(4);
  expect(dialogs[3]).toContain('YAML file loaded successfully!');
  await expect(page.locator('pre')).toContainText('recovered same filename');
  await expect(page.locator('pre')).toContainText('P9');
});
