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

/**
 * Parse a version string into its components for comparison.
 * Supports formats like "v1.0.0", "1.0.0", "v1.0", "1.0"
 * Returns null if the version cannot be parsed.
 */
export function parseVersion(version: string): { major: number; minor: number; patch: number } | null {
  const match = version.match(/^v?(\d+)\.(\d+)(?:\.(\d+))?/);
  if (!match) return null;
  return {
    major: parseInt(match[1], 10),
    minor: parseInt(match[2], 10),
    patch: match[3] !== undefined ? parseInt(match[3], 10) : 0,
  };
}

/**
 * Compare two version strings for sorting (descending order - newest first).
 * Returns negative if a > b, positive if a < b, 0 if equal.
 */
export function compareVersionsDescending(a: string, b: string): number {
  const versionA = parseVersion(a);
  const versionB = parseVersion(b);

  // Non-parseable versions go to the end
  if (!versionA && !versionB) return 0;
  if (!versionA) return 1;
  if (!versionB) return -1;

  // Compare major, minor, patch (descending)
  if (versionA.major !== versionB.major) return versionB.major - versionA.major;
  if (versionA.minor !== versionB.minor) return versionB.minor - versionA.minor;
  return versionB.patch - versionA.patch;
}

/**
 * Extract major.minor from a version string (e.g., "v1.0" from "v1.0.0" or "v1.0.0-5-gabcdef")
 */
export function getMajorMinor(version: string): string | null {
  const match = version.match(/^(v?\d+\.\d+)/);
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
      .sort(compareVersionsDescending);
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
    releases.sort((a, b) => compareVersionsDescending(a.version, b.version));

    return releases.map(({ label, url }) => ({ label, url }));
  } catch {
    // Silently fail - releases just won't show
    return [];
  }
}
