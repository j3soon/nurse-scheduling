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

import { Page } from '@playwright/test';

const STORAGE_KEY = 'nurse-scheduling-data';

type StoredState = {
  apiVersion: string;
  description: string;
  dates: {
    range: {
      startDate?: string;
      endDate?: string;
    };
    groups: Array<{ id: string; members: string[]; description: string }>;
  };
  people: {
    items: Array<{ id: string; description: string; history: string[] }>;
    groups: Array<{ id: string; members: string[]; description: string }>;
    history: string[];
  };
  shiftTypes: {
    items: Array<{ id: string; description: string }>;
    groups: Array<{ id: string; members: string[]; description: string }>;
  };
  preferences: Array<Record<string, unknown>>;
  export: {
    formatting: Array<Record<string, unknown>>;
  };
};

export async function seedSchedulingState(page: Page, state: StoredState) {
  const persisted = JSON.stringify({
    state,
    history: [state],
    currentHistoryIndex: 0,
  });

  await page.goto('/');
  await page.evaluate(
    ({ key, value }) => {
      window.localStorage.setItem(key, value);
    },
    { key: STORAGE_KEY, value: persisted }
  );
}

export async function disableModalDialogs(page: Page) {
  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });
}
