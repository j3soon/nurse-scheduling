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

'use client';

import { useState, useEffect } from 'react';
import { FiAlertTriangle, FiX } from 'react-icons/fi';
import { CURRENT_APP_VERSION, fetchLatestTag, getMajorMinor } from '@/utils/version';
import { WEBSITE_URL } from '@/constants/urls';

type VersionStatus = 'match' | 'older' | 'dev' | 'error' | null;

export default function VersionWarningBanner() {
  const [latestVersion, setLatestVersion] = useState<string | null>(null);
  const [isDismissed, setIsDismissed] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);

  useEffect(() => {
    const loadLatestTag = async () => {
      const tag = await fetchLatestTag();
      if (tag) {
        setLatestVersion(tag);
      } else {
        setFetchFailed(true);
      }
    };

    loadLatestTag();
  }, []);

  // Determine version status:
  // - 'error' -> failed to fetch latest tag
  // - 'match' -> exact match
  // - 'dev' -> same major.minor (e.g., "v1.0.0-5-gabcdef" matches "v1.0.1" on major.minor "v1.0")
  // - 'older' -> any other mismatch
  // - null -> still loading or unknown version
  const getVersionStatus = (): VersionStatus => {
    if (CURRENT_APP_VERSION === 'unknown') {
      return null;
    }

    if (fetchFailed) {
      return 'error';
    }

    if (!latestVersion) {
      return null;
    }

    // Exact match
    if (CURRENT_APP_VERSION === latestVersion) {
      return 'match';
    }

    // Dev build: current version has same major.minor as latest version
    const currentMajorMinor = getMajorMinor(CURRENT_APP_VERSION);
    const latestMajorMinor = getMajorMinor(latestVersion);
    if (currentMajorMinor && latestMajorMinor && currentMajorMinor === latestMajorMinor) {
      return 'dev';
    }

    // Any other mismatch is treated as older version
    return 'older';
  };

  const versionStatus = getVersionStatus();

  // Don't render if dismissed, versions match, or still loading
  if (isDismissed || !versionStatus || versionStatus === 'match') {
    return null;
  }

  // Determine banner colors based on version status
  const getBannerColors = () => {
    switch (versionStatus) {
      case 'error':
        return { bg: "bg-gray-100 border-b border-gray-300", text: "text-gray-800", button: "text-gray-700 hover:text-gray-900" };
      case 'older':
        return { bg: "bg-amber-100 border-b border-amber-300", text: "text-amber-800", button: "text-amber-700 hover:text-amber-900" };
      case 'dev':
        return { bg: "bg-blue-100 border-b border-blue-300", text: "text-blue-800", button: "text-blue-700 hover:text-blue-900" };
    }
  };

  const colors = getBannerColors();

  return (
    <div className={colors.bg}>
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between">
        <div className={`flex items-center gap-2 ${colors.text}`}>
          <FiAlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span className="text-sm">
            {versionStatus === 'error' ? (
              <>
                Unable to check for updates. You might be using an older version ({CURRENT_APP_VERSION}).{' '}
                <a
                  href={WEBSITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold underline hover:text-gray-900"
                >
                  Check releases
                </a>.
              </>
            ) : versionStatus === 'older' ? (
              <>
                You are using an older version ({CURRENT_APP_VERSION}). Latest stable release:{' '}
                <a
                  href={WEBSITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold underline hover:text-amber-900"
                >
                  {latestVersion}
                </a>.
              </>
            ) : (
              <>
                You are using a development version ({CURRENT_APP_VERSION}). Latest stable release:{' '}
                <a
                  href={WEBSITE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold underline hover:text-blue-900"
                >
                  {latestVersion}
                </a>.
              </>
            )}
          </span>
        </div>
        <button
          onClick={() => setIsDismissed(true)}
          className={`${colors.button} p-1`}
          title="Dismiss version warning"
        >
          <FiX className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
