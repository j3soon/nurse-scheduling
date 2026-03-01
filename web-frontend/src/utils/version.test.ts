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

import {
  compareVersionsDescending,
  fetchLatestTag,
  fetchReleaseBranches,
  getMajorMinor,
  parseVersion,
} from '@/utils/version';

describe('version utils', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('parses version strings and major/minor correctly', () => {
    expect(parseVersion('v1.2.3')).toEqual({ major: 1, minor: 2, patch: 3 });
    expect(parseVersion('2.5')).toEqual({ major: 2, minor: 5, patch: 0 });
    expect(parseVersion('invalid')).toBeNull();

    expect(getMajorMinor('v1.2.3-4-gabcd')).toBe('v1.2');
    expect(getMajorMinor('2.7.0')).toBe('2.7');
    expect(getMajorMinor('invalid')).toBeNull();
  });

  it('compares versions in descending semver order', () => {
    expect(compareVersionsDescending('v2.0.0', 'v1.9.9')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.0', 'v1.2.5')).toBeGreaterThan(0);
    expect(compareVersionsDescending('bad', 'v1.0.0')).toBeGreaterThan(0);
  });

  it('fetches latest tag sorted by semver', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'v1.0.0' }, { name: 'v1.3.0' }, { name: 'v1.2.9' }],
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchLatestTag()).resolves.toBe('v1.3.0');
  });

  it('returns null from fetchLatestTag on non-ok or errors', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(fetchLatestTag()).resolves.toBeNull();

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    await expect(fetchLatestTag()).resolves.toBeNull();

    expect(warnSpy).toHaveBeenCalled();
  });

  it('fetches and sorts release branches descending', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { name: 'main' },
        { name: 'release/1.2.0' },
        { name: 'release/1.10.0' },
        { name: 'release/0.9.0' },
      ],
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchReleaseBranches()).resolves.toEqual([
      { label: 'v1.10.0', url: 'https://release-1-10-0.nursescheduling.org' },
      { label: 'v1.2.0', url: 'https://release-1-2-0.nursescheduling.org' },
      { label: 'v0.9.0', url: 'https://release-0-9-0.nursescheduling.org' },
    ]);
  });

  it('returns [] from fetchReleaseBranches on failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    await expect(fetchReleaseBranches()).resolves.toEqual([]);

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    await expect(fetchReleaseBranches()).resolves.toEqual([]);
  });
});
