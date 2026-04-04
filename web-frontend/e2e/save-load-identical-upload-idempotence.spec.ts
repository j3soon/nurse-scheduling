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

test('uploading the same YAML twice leaves the resulting preview stable', async ({ page }) => {
  /*
   * Steps:
   * 1. Capture the current valid YAML preview.
   * 2. Upload that exact same YAML once and record the resulting preview.
   * 3. Upload the same YAML again in the same session.
   * 4. Confirm the preview remains unchanged.
   */
  await page.goto('/save-and-load');
  const originalYaml = await page.locator('pre').textContent();
  expect(originalYaml).toContain('apiVersion:');

  const uploadInput = page.locator('input[type="file"]');
  await uploadInput.setInputFiles({
    name: 'same-1.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(originalYaml ?? '', 'utf8'),
  });
  const firstPreview = await page.locator('pre').textContent();

  await uploadInput.setInputFiles({
    name: 'same-2.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(originalYaml ?? '', 'utf8'),
  });
  await expect(page.locator('pre')).toContainText((firstPreview ?? '').split('\n')[0]);
  const secondPreview = await page.locator('pre').textContent();
  expect(secondPreview).toBe(firstPreview);
});
