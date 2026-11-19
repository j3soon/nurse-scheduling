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

import { DataType, type DateRange } from '@/types/scheduling';
import { getDateIdForRange } from '@/utils/calendar';
import { mapReferenceIdTree } from '@/utils/referenceIds';
import type { ScheduleSpecState } from './scheduleSpecState';
import { applyReferencesForIdDeletion } from './schedulingReferenceUpdates';

function dateIdsByIsoDate(range: DateRange): Map<string, string> {
  const ids = new Map<string, string>();
  const { startDate, endDate } = range;
  if (!startDate || !endDate) return ids;

  for (const date = new Date(startDate); date <= endDate; date.setUTCDate(date.getUTCDate() + 1)) {
    ids.set(date.toISOString().split('T')[0], getDateIdForRange(date, range));
  }
  return ids;
}

function mapDateReferences(state: ScheduleSpecState, mapId: (id: string) => string): ScheduleSpecState {
  const mapIds = (ids: string[]) =>
    Array.isArray(ids) ? mapReferenceIdTree(ids, mapId) as string[] : ids;
  return {
    ...state,
    dates: {
      ...state.dates,
      groups: state.dates.groups.map(group => ({ ...group, members: mapIds(group.members) })),
    },
    preferences: state.preferences.map(pref => {
      if ('date' in pref) return { ...pref, date: mapIds(pref.date) };
      if ('countDates' in pref) return { ...pref, countDates: mapIds(pref.countDates) };
      return pref;
    }),
    ...(state.export && {
      export: {
        ...state.export,
        formatting: state.export.formatting?.map(rule => 'dates' in rule
          ? { ...rule, dates: mapIds(rule.dates) }
          : rule),
        extraColumns: state.export.extraColumns?.map(rule => ({ ...rule, countDates: mapIds(rule.countDates) })),
      },
    }),
  };
}

// The optimizer resolves a named group before it parses a range expression.
const DATE_RANGE_EXPRESSION = new RegExp(String.raw`^[\p{Decimal_Number}-]+~[\p{Decimal_Number}-]+\n?$`, 'u');

export function findDateRangeExpressionPath(state: ScheduleSpecState): string | undefined {
  const groupIds = new Set<string>();
  const seenArrays = new WeakSet<unknown[]>();
  const find = (value: unknown, path: string): string | undefined => {
    if (Array.isArray(value) && !seenArrays.has(value)) {
      seenArrays.add(value);
      for (let index = 0; index < value.length; index++) {
        const found = find(value[index], `${path}[${index}]`);
        if (found) return found;
      }
    }
    if (typeof value === 'string' && !groupIds.has(value) && DATE_RANGE_EXPRESSION.test(value)) return path;
    return undefined;
  };

  for (const [index, group] of state.dates.groups.entries()) {
    const found = find(group.members, `dates.groups[${index}].members`);
    if (found) return found;
    groupIds.add(String(group.id));
  }
  for (const [index, pref] of state.preferences.entries()) {
    const found = 'date' in pref
      ? find(pref.date, `preferences[${index}].date`)
      : 'countDates' in pref ? find(pref.countDates, `preferences[${index}].countDates`) : undefined;
    if (found) return found;
  }
  for (const [index, rule] of (state.export?.formatting ?? []).entries()) {
    if ('dates' in rule) {
      const found = find(rule.dates, `export.formatting[${index}].dates`);
      if (found) return found;
    }
  }
  for (const [index, column] of (state.export?.extraColumns ?? []).entries()) {
    const found = find(column.countDates, `export.extraColumns[${index}].countDates`);
    if (found) return found;
  }
  return undefined;
}

export function normalizeDateReferences(state: ScheduleSpecState): ScheduleSpecState {
  const aliases = new Map<string, string>();
  for (const [isoDate, id] of dateIdsByIsoDate(state.dates.range)) {
    aliases.set(isoDate, id);
    // The optimizer accepts month-day selectors in a single year and day
    // selectors in a single month. Use the same bounds as the generated IDs.
    if (id.length <= 5) aliases.set(isoDate.slice(5), id);
    if (id.length === 2) {
      aliases.set(id, id);
      aliases.set(String(Number(id)), id);
    }
  }
  // Preserve references to imported groups with date-shaped IDs so users can
  // rename the groups in the browser.
  for (const group of state.dates.groups) aliases.delete(group.id);

  return mapDateReferences(state, id => {
    const input: unknown = id;
    // js-yaml parses unquoted ISO dates as Date objects. Convert these before
    // browser storage copies their enumerable fields into an empty object.
    if (input instanceof Date && Number.isFinite(input.getTime())) {
      const isoDate = input.toISOString().split('T')[0];
      return aliases.get(isoDate) ?? isoDate;
    }
    return aliases.get(typeof input === 'number' ? String(input) : id) ?? id;
  });
}

export function remapDateReferences(state: ScheduleSpecState, range: DateRange): ScheduleSpecState {
  const nextIds = dateIdsByIsoDate(range);
  const removed = new Set<string>();
  const renamed = new Map<string, string>();
  for (const [isoDate, id] of dateIdsByIsoDate(state.dates.range)) {
    const nextId = nextIds.get(isoDate);
    if (nextId === undefined) removed.add(id);
    else if (nextId !== id) renamed.set(id, nextId);
  }

  const withNewRange = {
    ...state,
    dates: {
      ...state.dates,
      range,
      groups: state.dates.groups.map(group => ({
        ...group,
        members: group.members.filter(id => !removed.has(id)),
      })),
    },
  };
  const prunedState = applyReferencesForIdDeletion(withNewRange, DataType.DATES, [...removed]);
  return renamed.size > 0 ? mapDateReferences(prunedState, id => renamed.get(id) ?? id) : prunedState;
}
