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

export interface OrderedEntry {
  id: string;
}

export function getOrderedEntries(data: { items: OrderedEntry[]; groups: OrderedEntry[] }): OrderedEntry[] {
  return [...data.items, ...data.groups];
}

export function sortIdsByEntryOrder(ids: string[] | undefined, entries: OrderedEntry[]): string[] {
  if (ids === undefined || ids === null) return [];
  if (!Array.isArray(ids)) return [String(ids)];

  const entryOrder = new Map(entries.map((entry, index) => [entry.id, index]));
  return [...ids].sort((a, b) => {
    const orderA = entryOrder.get(a) ?? Number.MAX_SAFE_INTEGER;
    const orderB = entryOrder.get(b) ?? Number.MAX_SAFE_INTEGER;
    return orderA - orderB;
  });
}

// These fields are arrays for schema consistency, but callers use this helper
// only for preference fields that should contain exactly one ID.
export function compareFirstIdByEntryOrder(a: string[], b: string[], entries: OrderedEntry[]): number {
  const entryOrder = new Map(entries.map((entry, index) => [entry.id, index]));
  const orderA = entryOrder.get(a[0]) ?? Number.MAX_SAFE_INTEGER;
  const orderB = entryOrder.get(b[0]) ?? Number.MAX_SAFE_INTEGER;
  return orderA - orderB;
}

export function sortPairsByFirstIdEntryOrder<T>(
  pairs: Array<[string, T]> | undefined,
  entries: OrderedEntry[]
): Array<[string, T]> | undefined {
  if (!pairs) return pairs;

  const entryOrder = new Map(entries.map((entry, index) => [entry.id, index]));
  return [...pairs].sort((a, b) => {
    // Each pair is [entityId, value]; sort by the entity ID.
    const orderA = entryOrder.get(a[0]) ?? Number.MAX_SAFE_INTEGER;
    const orderB = entryOrder.get(b[0]) ?? Number.MAX_SAFE_INTEGER;
    return orderA - orderB;
  });
}
