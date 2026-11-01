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

export function loadLegacyScheduleSpec<T>(storage: Storage, key: string, decode: (raw: string) => T): T | null {
  const oldKey = key.replace('nurse-scheduling-spec', 'nurse-scheduling-data');
  const raw = storage.getItem(oldKey);
  // Decode before writing. Another tab can save or finish migrating during this work.
  const value = raw === null ? null : decode(raw);
  const current = storage.getItem(key);
  if (current !== null) return decode(current);
  if (raw === null) return null;
  try {
    storage.setItem(key, raw);
    storage.removeItem(oldKey);
  } catch { /* Storage can be full or disabled. Keep the old record for retry. */ }
  return value;
}
