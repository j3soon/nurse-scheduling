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

test('uploading YAML and immediately downloading yields the uploaded state', async ({ page }) => {
  /*
   * Steps:
   * 1. Capture a valid YAML payload from the real page and confirm the original preview content.
   * 2. Upload that same valid YAML back through the real control.
   * 3. Download immediately through the real control.
   * 4. Confirm the downloaded content reflects the uploaded state.
   */
  await page.goto('/save-and-load');
  const yamlText = await page.locator('pre').textContent();
  expect(yamlText).toContain('apiVersion:');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'uploaded.yaml',
    mimeType: 'application/x-yaml',
    buffer: Buffer.from(yamlText ?? '', 'utf8'),
  });

  await expect(page.locator('pre')).toContainText((yamlText ?? '').split('\n')[0]);

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download' }).click();
  const download = await downloadPromise;
  const content = await download.createReadStream();
  let downloadedYaml = '';
  if (content) {
    for await (const chunk of content) {
      downloadedYaml += chunk.toString();
    }
  }

  expect(downloadedYaml).toContain((yamlText ?? '').split('\n')[0]);
  expect(downloadedYaml).toContain('apiVersion:');
});
