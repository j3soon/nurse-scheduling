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

// External URLs used throughout the application.

// GitHub URLs
export const GITHUB_REPO_URL = 'https://github.com/j3soon/nurse-scheduling';
export const GITHUB_TAGS_URL = 'https://github.com/j3soon/nurse-scheduling/tags';
export const GITHUB_LICENSE_URL = 'https://github.com/j3soon/nurse-scheduling/blob/dev/LICENSE';
export const GITHUB_PRIVACY_URL = 'https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md';
export const GITHUB_CODE_FREQUENCY_URL = 'https://github.com/j3soon/nurse-scheduling/graphs/code-frequency';
export const GITHUB_ACKNOWLEDGMENTS_URL = 'https://github.com/j3soon/nurse-scheduling#acknowledgments';
export const GITHUB_AUTHOR_URL = 'https://github.com/j3soon';
// GitHub Tags API URL for fetching latest tag
export const GITHUB_TAGS_API_URL = 'https://api.github.com/repos/j3soon/nurse-scheduling/tags';
// GitHub Branches API URL for fetching release branches
export const GITHUB_BRANCHES_API_URL = 'https://api.github.com/repos/j3soon/nurse-scheduling/branches';

// Website URLs
export const WEBSITE_URL = 'https://nursescheduling.org';

// Netlify publishes Zensical at /docs. Local development serves it separately.
const DEFAULT_DOCUMENTATION_BASE_URL = process.env.NODE_ENV === 'development'
  ? 'http://127.0.0.1:8003/docs'
  : '/docs';
const DOCUMENTATION_BASE_URL = (
  process.env.NEXT_PUBLIC_DOCS_BASE_URL || DEFAULT_DOCUMENTATION_BASE_URL
).replace(/\/+$/, '');

export const DOCUMENTATION_URLS = {
  home: `${DOCUMENTATION_BASE_URL}/`,
  dates: `${DOCUMENTATION_BASE_URL}/user-guide/dates/`,
  people: `${DOCUMENTATION_BASE_URL}/user-guide/people/`,
  shiftTypes: `${DOCUMENTATION_BASE_URL}/user-guide/shift-types/`,
  shiftTypeRequirements: `${DOCUMENTATION_BASE_URL}/user-guide/shift-type-requirements/`,
  shiftRequests: `${DOCUMENTATION_BASE_URL}/user-guide/shift-requests/`,
  shiftTypeSuccessions: `${DOCUMENTATION_BASE_URL}/user-guide/shift-type-successions/`,
  shiftCounts: `${DOCUMENTATION_BASE_URL}/user-guide/shift-counts/`,
  shiftAffinities: `${DOCUMENTATION_BASE_URL}/user-guide/shift-affinities/`,
  exportLayout: `${DOCUMENTATION_BASE_URL}/user-guide/export-layout/`,
  saveAndLoad: `${DOCUMENTATION_BASE_URL}/user-guide/save-and-load/`,
  optimizeAndExport: `${DOCUMENTATION_BASE_URL}/user-guide/optimize-and-export/`,
  experimentalAi: `${DOCUMENTATION_BASE_URL}/user-guide/experimental-ai/`,
} as const;

// Build URLs for environment switching (static entries)
export const STATIC_BUILD_URLS = [
  { label: 'local', url: 'http://localhost:3000' },
  { label: 'dev', url: 'https://dev.nursescheduling.org' },
  { label: 'main', url: 'https://nursescheduling.org' },
];

// License URLs
export const AGPL_LICENSE_URL = 'https://www.gnu.org/licenses/agpl-3.0.html';
