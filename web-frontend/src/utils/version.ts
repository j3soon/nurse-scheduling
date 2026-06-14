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

import { GITHUB_TAGS_API_URL, GITHUB_BRANCHES_API_URL } from '@/constants/urls';

// Current application version from environment variable.
export const CURRENT_APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || 'unknown';

// Type for release branch entries
export type BuildEntry = { label: string; url: string };

export type VersionParts = {
  major: number | null;
  minor: number | null;
  patch: number | null;
  commitsAfterTag: number;
  commitId: string | null;
  dirty: boolean;
};

export function areBuildOriginsEquivalent(firstUrl: string, secondUrl: string): boolean {
  try {
    const firstOrigin = new URL(firstUrl).origin;
    const secondOrigin = new URL(secondUrl).origin;
    const firstHostname = new URL(firstOrigin).hostname;
    const secondHostname = new URL(secondOrigin).hostname;

    if (firstHostname === 'localhost' && secondHostname === 'localhost') {
      return true;
    }

    return firstOrigin === secondOrigin;
  } catch {
    return firstUrl.replace(/\/$/, '') === secondUrl.replace(/\/$/, '');
  }
}

const HASH_ONLY_PATTERN = /^[0-9a-fA-F]{7,}$/;
const TAGGED_COMMIT_PATTERN = /^(v\d+\.\d+\.\d+)-(\d+)-g([0-9a-fA-F]{7,})$/;
const TAG_PATTERN = /^v(\d+)\.(\d+)\.(\d+)$/;

export function parseVersionParts(version: string): VersionParts {
  const isDirty = version.endsWith('-dirty');
  const cleanVersion = isDirty ? version.slice(0, -'-dirty'.length) : version;

  if (HASH_ONLY_PATTERN.test(cleanVersion)) {
    return {
      major: null,
      minor: null,
      patch: null,
      commitsAfterTag: 0,
      commitId: cleanVersion,
      dirty: isDirty,
    };
  }

  const taggedCommitMatch = cleanVersion.match(TAGGED_COMMIT_PATTERN);
  if (taggedCommitMatch) {
    const tagVersionMatch = taggedCommitMatch[1].match(TAG_PATTERN)!;
    return {
      major: parseInt(tagVersionMatch[1], 10),
      minor: parseInt(tagVersionMatch[2], 10),
      patch: parseInt(tagVersionMatch[3], 10),
      commitsAfterTag: parseInt(taggedCommitMatch[2], 10),
      commitId: taggedCommitMatch[3],
      dirty: isDirty,
    };
  }

  const tagVersionMatch = cleanVersion.match(TAG_PATTERN);
  return {
    major: tagVersionMatch ? parseInt(tagVersionMatch[1], 10) : null,
    minor: tagVersionMatch ? parseInt(tagVersionMatch[2], 10) : null,
    patch: tagVersionMatch ? parseInt(tagVersionMatch[3], 10) : null,
    commitsAfterTag: 0,
    commitId: null,
    dirty: isDirty,
  };
}

/**
 * Compare two version strings for sorting (descending order - newest first).
 * Supports release tags and git describe output such as
 * "v1.2.3-4-gabcdef0-dirty"; hash-only versions sort after tagged versions.
 *
 * Rules:
 * - "Semver/tagged" includes plain vX.Y.Z and git describe vX.Y.Z-N-gHASH versions, with optional -dirty suffixes.
 * - Semver/tagged versions sort before hash-only versions.
 * - Hash-only versions sort before unsupported formats.
 * - Semver/tagged versions order by major/minor/patch, then commits after tag.
 * - Dirty acts as a half-step newer only when semver, commit count, and commit id match.
 * - Commit ids identify builds but do not imply recency; different commit ids with otherwise matching orderable fields return null.
 * - Hash-only versions can only compare equal or dirty-vs-clean when the commit id matches.
 * - Unsupported formats cannot be ordered against each other.
 *
 * Returns negative if a > b, positive if a < b, 0 if equal, or null if
 * both versions are valid but their commit ids make recency unknowable.
 */
export function compareVersionsDescending(a: string, b: string): number | null {
  const versionA = parseVersionParts(a);
  const versionB = parseVersionParts(b);

  const aHasSemver = versionA.major !== null;
  const bHasSemver = versionB.major !== null;

  if (!aHasSemver && bHasSemver) return 1;
  if (aHasSemver && !bHasSemver) return -1;

  // Versions without semver cannot be ordered by recency; only identical commit ids can compare equal.
  if (!aHasSemver && !bHasSemver) {
    if (versionA.commitId === null && versionB.commitId === null) return null;
    if (versionA.commitId === null) return 1;
    if (versionB.commitId === null) return -1;
    if (versionA.commitId?.toLowerCase() !== versionB.commitId?.toLowerCase()) {
      return null;
    }
    if (versionA.dirty !== versionB.dirty) {
      return versionA.dirty ? -1 : 1;
    }
    return 0;
  }

  // Compare major, minor, patch (descending)
  if (versionA.major! !== versionB.major!) return versionB.major! - versionA.major!;
  if (versionA.minor! !== versionB.minor!) return versionB.minor! - versionA.minor!;
  if (versionA.patch! !== versionB.patch!) return versionB.patch! - versionA.patch!;
  if (versionA.commitsAfterTag !== versionB.commitsAfterTag) {
    return versionB.commitsAfterTag! - versionA.commitsAfterTag!;
  }

  if (versionA.commitId?.toLowerCase() !== versionB.commitId?.toLowerCase()) {
    return null;
  }

  if (versionA.dirty !== versionB.dirty) {
    return versionA.dirty ? -1 : 1;
  }
  return 0;
}

/**
 * Extract major.minor from a vX.Y.Z version string (e.g., "v1.0" from "v1.0.0" or "v1.0.0-5-gabcdef").
 */
export function getMajorMinor(version: string): string | null {
  const match = version.match(/^(v\d+\.\d+)/);
  return match ? match[1] : null;
}

/**
 * Fetch the latest tag from GitHub, sorted by semver (newest first).
 * Returns the latest tag name or null if fetch fails.
 */
export async function fetchLatestTag(): Promise<string | null> {
  try {
    const response = await fetch(GITHUB_TAGS_API_URL);
    if (!response.ok) {
      console.warn('Failed to fetch latest tag:', response.status);
      return null;
    }
    const tags: { name: string }[] = await response.json();
    if (tags.length === 0) {
      return null;
    }
    // Sort tags by semver (descending) and return the latest
    const sortedTags = tags
      .map((t) => t.name)
      .sort((a, b) => compareVersionsDescending(a, b) ?? 0);
    return sortedTags[0] || null;
  } catch (err) {
    console.warn('Failed to fetch latest tag:', err);
    return null;
  }
}

/**
 * Fetch release branches from GitHub and return them as BuildEntry objects,
 * sorted by semver (newest first).
 */
export async function fetchReleaseBranches(): Promise<BuildEntry[]> {
  try {
    const response = await fetch(GITHUB_BRANCHES_API_URL);
    if (!response.ok) {
      return [];
    }
    const branches: { name: string }[] = await response.json();
    const releases = branches
      .map((b) => b.name.match(/^release\/(.+)$/))
      .filter((m): m is RegExpMatchArray => m !== null)
      .map((m) => ({
        version: m[1],
        label: `v${m[1]}`,
        url: `https://release-${m[1].replace(/\./g, '-')}.nursescheduling.org`,
      }));

    // Sort by version (descending - newest first)
    releases.sort((a, b) => compareVersionsDescending(`v${a.version}`, `v${b.version}`) ?? 0);

    return releases.map(({ label, url }) => ({ label, url }));
  } catch {
    // Silently fail - releases just won't show
    return [];
  }
}
