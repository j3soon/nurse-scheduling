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

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const zensicalConfig = readFileSync(resolve(process.cwd(), '../zensical.toml'), 'utf8');

function getProjectSetting(name: string): string {
  const value = zensicalConfig.match(new RegExp(`^${name} = "([^"]+)"$`, 'm'))?.[1];

  if (!value) {
    throw new Error(`Missing ${name} in zensical.toml`);
  }

  return value;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('documentation URLs', () => {
  it('keeps the development URL synchronized with the Zensical server', async () => {
    const sitePath = new URL(getProjectSetting('site_url')).pathname.replace(/\/$/, '');
    const expectedBaseUrl = `http://${getProjectSetting('dev_addr')}${sitePath}`;
    vi.stubEnv('NODE_ENV', 'development');

    const { DOCUMENTATION_URLS } = await import('./urls');

    expect(DOCUMENTATION_URLS.home).toBe(`${expectedBaseUrl}/`);
  });
});
