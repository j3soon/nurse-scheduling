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

export type ReferenceIdTree = string | ReferenceIdTree[];

export function hasNestedReferenceIds(value: unknown): boolean {
  return Array.isArray(value) && value.some(Array.isArray);
}

export function mapReferenceIdTree(
  value: ReferenceIdTree,
  mapId: (id: string) => string
): ReferenceIdTree {
  return Array.isArray(value)
    ? value.map(item => mapReferenceIdTree(item, mapId))
    : mapId(value);
}

export function filterReferenceIdTree(
  value: ReferenceIdTree,
  keepId: (id: string) => boolean
): ReferenceIdTree {
  return Array.isArray(value)
    ? value
      .map(item => filterReferenceIdTree(item, keepId))
      .filter(item => Array.isArray(item) ? item.length > 0 : keepId(item))
    : keepId(value) ? value : [];
}
