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

import { test, expect } from './test';

test('sequential YAML uploads replace state cleanly rather than merging leftovers', async ({ page }) => {
  /*
   * Steps:
   * 1. Upload one valid YAML file and confirm its people are present.
   * 2. Upload a second distinct YAML file in the same session.
   * 3. Confirm the second state is present.
   * 4. Confirm entities unique to the first upload are gone.
   */
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  const yamlA = `apiVersion: test\ndescription: first state\ndates:\n  range:\n    startDate: 2026-05-01\n    endDate: 2026-05-01\n  groups: []\npeople:\n  items:\n    - id: P1\n      description: First\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: D\n      description: Day\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;
  const yamlB = `apiVersion: test\ndescription: second state\ndates:\n  range:\n    startDate: 2026-06-01\n    endDate: 2026-06-01\n  groups: []\npeople:\n  items:\n    - id: P2\n      description: Second\n      history: []\n  groups: []\n  history: []\nshiftTypes:\n  items:\n    - id: N\n      description: Night\n  groups: []\npreferences:\n  - type: at most one shift per day\nexport:\n  formatting: []\n`;

  await page.goto('/save-and-load');
  const uploadInput = page.locator('input[type="file"]');
  await uploadInput.setInputFiles({ name: 'first.yaml', mimeType: 'application/x-yaml', buffer: Buffer.from(yamlA, 'utf8') });
  await expect.poll(() => dialogs.length).toBe(2);
  await expect(page.locator('pre')).toContainText('first state');
  await expect(page.locator('pre')).toContainText('P1');

  await uploadInput.setInputFiles({ name: 'second.yaml', mimeType: 'application/x-yaml', buffer: Buffer.from(yamlB, 'utf8') });
  await expect.poll(() => dialogs.length).toBe(4);
  await expect(page.locator('pre')).toContainText('second state');
  await expect(page.locator('pre')).toContainText('P2');
  await expect(page.locator('pre')).toContainText('id: N');
  await expect(page.locator('pre')).not.toContainText('P1');
  await expect(page.locator('pre')).not.toContainText('id: D');
});
