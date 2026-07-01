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

export interface ServerHealthResponse {
  status: string;
  version: string;
  apiVersion?: string;
  appVersion: string;
}

export interface ServerHealthCheckResult {
  endpoint: string;
  index: number;
  health: ServerHealthResponse;
}

export const LOCAL_BACKEND_API_URL = 'http://localhost:8000';
export const PRODUCTION_BACKEND_API_URL = 'https://api.nursescheduling.org';
export const SHOULD_DISABLE_PRODUCTION_BACKEND_API = process.env.NODE_ENV === 'test'
  || process.env.NEXT_PUBLIC_DISABLE_HOSTED_OPTIMIZE_API === '1';
export const BACKEND_API_CANDIDATES = SHOULD_DISABLE_PRODUCTION_BACKEND_API
  ? [LOCAL_BACKEND_API_URL]
  : [LOCAL_BACKEND_API_URL, PRODUCTION_BACKEND_API_URL];
export const INITIAL_BACKEND_API_URL = BACKEND_API_CANDIDATES[0];

export function selectOfflineFallbackBackendApiUrl(candidates: string[]): string {
  return candidates.includes(PRODUCTION_BACKEND_API_URL)
    ? PRODUCTION_BACKEND_API_URL
    : candidates[0];
}

export function selectPreferredServer(results: ServerHealthCheckResult[]): ServerHealthCheckResult | undefined {
  return [...results].sort((a, b) => a.index - b.index)[0];
}
