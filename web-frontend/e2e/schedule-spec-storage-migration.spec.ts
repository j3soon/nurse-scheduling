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
import { seedMinimalScheduleSpecState } from './helpers';

for (const legacyRemoved of [false, true]) {
  test(`migration preserves another tab's newer save (legacy removed: ${legacyRemoved})`, async ({ page }) => {
    await seedMinimalScheduleSpecState(page);
    await page.goto('/save-and-load');
    await expect(page.locator('pre')).toContainText('minimal E2E schedule');
    const setup = await page.evaluate(() => {
      const namespace = window.__PLAYWRIGHT_WORKER_NAMESPACE__;
      const currentKey = namespace ? `nurse-scheduling-spec__${namespace}` : 'nurse-scheduling-spec';
      const legacyKey = currentKey.replace('nurse-scheduling-spec', 'nurse-scheduling-data');
      const stored = JSON.parse(localStorage.getItem(currentKey)!);
      stored.state.description = 'Requirements before migration';
      stored.history = [structuredClone(stored.state)];
      stored.currentHistoryIndex = 0;
      const legacyRaw = JSON.stringify(stored);
      stored.state.description = 'Newer requirements saved by another tab';
      stored.history.push(stored.state);
      stored.currentHistoryIndex = 1;
      const newerRaw = JSON.stringify(stored);
      localStorage.setItem(legacyKey, legacyRaw);
      localStorage.removeItem(currentKey);
      return { currentKey, legacyKey, legacyRaw, newerRaw };
    });
    await page.addInitScript(({ currentKey, legacyKey, newerRaw, legacyRemoved }) => {
      const getItem = Storage.prototype.getItem;
      let published = false;
      Storage.prototype.getItem = function (key: string) {
        const stored = getItem.call(this, key);
        // Reproduce another tab saving after the loader's initial current-key read.
        if (key === legacyKey && !published) {
          published = true;
          this.setItem(currentKey, newerRaw);
          if (legacyRemoved) {
            this.removeItem(legacyKey);
            return null;
          }
        }
        return stored;
      };
    }, { ...setup, legacyRemoved });

    await page.goto('/save-and-load');
    await expect(page.locator('pre')).toContainText('Newer requirements saved by another tab');
    await expect(page.locator('pre')).not.toContainText('Requirements before migration');
    expect(await page.evaluate(key => localStorage.getItem(key), setup.currentKey)).toBe(setup.newerRaw);
    expect(await page.evaluate(key => localStorage.getItem(key), setup.legacyKey)).toBe(legacyRemoved ? null : setup.legacyRaw);
    await page.reload();
    await expect(page.locator('pre')).toContainText('Newer requirements saved by another tab');
  });
}
