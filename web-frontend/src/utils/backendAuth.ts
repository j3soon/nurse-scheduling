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

// This code is mostly AI generated.

export interface AuthRequirement {
  required: boolean;
  scheme: string;
}

export const SUPPORTED_AUTH_SCHEME = 'bearer';

// Backends that predate authentication omit the descriptor. Treating those as open
// preserves compatibility while current deployments can require a bearer credential.
export function parseAuthRequirement(value: unknown): AuthRequirement | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null;
  }
  const candidate = value as Partial<AuthRequirement>;
  if (typeof candidate.required !== 'boolean') {
    return null;
  }
  return {
    required: candidate.required,
    scheme: typeof candidate.scheme === 'string' ? candidate.scheme.toLowerCase() : SUPPORTED_AUTH_SCHEME,
  };
}

export function buildAuthHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
