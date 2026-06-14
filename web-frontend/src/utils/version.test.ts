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
  areBuildOriginsEquivalent,
  compareVersionsDescending,
  fetchLatestTag,
  fetchReleaseBranches,
  getMajorMinor,
  parseVersionParts,
} from '@/utils/version';

describe('version utils', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('treats localhost origins on any port as the same build', () => {
    expect(areBuildOriginsEquivalent('http://localhost:3000', 'http://localhost:3001')).toBe(true);
    expect(areBuildOriginsEquivalent('http://localhost:3000/', 'https://localhost:4443')).toBe(true);
    expect(areBuildOriginsEquivalent('http://localhost:3000', 'http://127.0.0.1:3000')).toBe(false);
  });

  it('compares non-localhost build origins exactly', () => {
    expect(areBuildOriginsEquivalent('https://nursescheduling.org/', 'https://nursescheduling.org')).toBe(true);
    expect(areBuildOriginsEquivalent('https://dev.nursescheduling.org', 'https://nursescheduling.org')).toBe(false);
    expect(areBuildOriginsEquivalent('not-a-url/', 'not-a-url')).toBe(true);
  });

  it('extracts major/minor from version strings', () => {
    expect(getMajorMinor('v1.2.3-4-gabcd')).toBe('v1.2');
    expect(getMajorMinor('2.7.0')).toBeNull();
    expect(getMajorMinor('invalid')).toBeNull();
  });

  it('parses git describe version parts for display and comparison', () => {
    expect(parseVersionParts('v1.2.3-4-gAbC1234-dirty')).toEqual({
      major: 1,
      minor: 2,
      patch: 3,
      commitsAfterTag: 4,
      commitId: 'AbC1234',
      dirty: true,
    });
    expect(parseVersionParts('deadbeef')).toEqual({
      major: null,
      minor: null,
      patch: null,
      commitsAfterTag: 0,
      commitId: 'deadbeef',
      dirty: false,
    });
    expect(parseVersionParts('v1.2-4-gabcd')).toEqual({
      major: null,
      minor: null,
      patch: null,
      commitsAfterTag: 0,
      commitId: null,
      dirty: false,
    });
    expect(parseVersionParts('123')).toEqual({
      major: null,
      minor: null,
      patch: null,
      commitsAfterTag: 0,
      commitId: null,
      dirty: false,
    });
  });

  it('compares versions in descending semver order', () => {
    expect(compareVersionsDescending('v2.0.0', 'v1.9.9')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.0', 'v1.2.5')).toBeGreaterThan(0);
    expect(compareVersionsDescending('bad', 'v1.0.0')).toBeGreaterThan(0);
  });

  it('compares git describe versions by tag and commit distance', () => {
    expect(compareVersionsDescending('v1.2.3-4-gabc1234', 'v1.2.3')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.3-4-gabc1234', 'v1.2.3-2-gdef5678')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.4', 'v1.2.3-10-gabc1234')).toBeLessThan(0);
  });

  it('treats dirty git describe versions as half a commit newer', () => {
    expect(compareVersionsDescending('v1.2.3-dirty', 'v1.2.3')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.3-1-gabc1234', 'v1.2.3-dirty')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.3-4-gabc1234-dirty', 'v1.2.3-4-gabc1234')).toBeLessThan(0);
    expect(compareVersionsDescending('v1.2.3-4-gabc1234-dirty', 'v1.2.3-2-gdef5678')).toBeLessThan(0);
  });

  it('uses commit ids to distinguish otherwise matching git describe versions', () => {
    expect(compareVersionsDescending('v1.2.3-4-gabc1234', 'v1.2.3-4-gabc1234')).toBe(0);
    expect(compareVersionsDescending('v1.2.3-4-gabc1234', 'v1.2.3-4-gABC1234')).toBe(0);
    expect(compareVersionsDescending('v1.2.3-4-gabc1234', 'v1.2.3-4-gdef5678')).toBeNull();
  });

  it('sorts non git-describe fallback versions after tagged versions', () => {
    expect(compareVersionsDescending('v0.0.0-unknown', 'v1.0.0')).toBeGreaterThan(0);
    expect(compareVersionsDescending('v0.0.1-unknown', 'v0.0.0-unknown')).toBeNull();
  });

  it('sorts hash-only versions after tagged versions', () => {
    expect(compareVersionsDescending('abc1234', 'v1.2.3-4-gabc1234')).toBeGreaterThan(0);
    expect(compareVersionsDescending('1234567', 'v1.2.3-4-gabc1234')).toBeGreaterThan(0);
    expect(compareVersionsDescending('abc1234', 'abc1234')).toBe(0);
    expect(compareVersionsDescending('abc1234-dirty', 'abc1234')).toBeLessThan(0);
    expect(compareVersionsDescending('abc1234-dirty', 'def5678')).toBeNull();
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
