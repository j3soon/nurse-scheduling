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
import type { Translator } from '@/i18n/messages';
import { DATE_RANGE_EXPRESSION, getDateIdForRange, hasNonAsciiDateDigits, isDateSelectorShape } from '@/utils/calendar';
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

export type DateReferenceIssue = { path: string; kind: 'range-expression' | 'non-ascii-digits' | 'group-id' };

export function dateReferenceIssueMessage(issue: DateReferenceIssue, t: Translator): string {
  switch (issue.kind) {
    case 'group-id':
      return t("Rename the date group at {value0} so its ID does not look like a date or date range expression.", { value0: issue.path });
    case 'non-ascii-digits':
      return t("Use ASCII digits (0-9) for the date at {value0}.", { value0: issue.path });
    case 'range-expression':
      return t("{value0} uses a date range expression. Use individual dates or a named date group.", { value0: issue.path });
  }
}

export function findDateReferenceIssue(state: ScheduleSpecState): DateReferenceIssue | undefined {
  const seenArrays = new WeakSet<unknown[]>();
  const find = (value: unknown, path: string): DateReferenceIssue | undefined => {
    if (Array.isArray(value) && !seenArrays.has(value)) {
      seenArrays.add(value);
      for (let index = 0; index < value.length; index++) {
        const found = find(value[index], `${path}[${index}]`);
        if (found) return found;
      }
    }
    if (hasNonAsciiDateDigits(value)) return { path, kind: 'non-ascii-digits' };
    if (typeof value === 'string' && DATE_RANGE_EXPRESSION.test(value)) return { path, kind: 'range-expression' };
    return undefined;
  };

  for (const [index, group] of state.dates.groups.entries()) {
    const id: unknown = group.id;
    if (id instanceof Date || isDateSelectorShape(String(id))) {
      return { path: `dates.groups[${index}].id`, kind: 'group-id' };
    }
    const found = find(group.members, `dates.groups[${index}].members`);
    if (found) return found;
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
  // Preserve IDs from older browser drafts so users can rename their groups.
  const groupIds = new Set(state.dates.groups.map(group => group.id));
  const getAlias = (id: string) => {
    if (groupIds.has(id)) return id;
    const alias = aliases.get(id.endsWith('\n') ? id.slice(0, -1) : id);
    return alias !== undefined && !groupIds.has(alias) ? alias : undefined;
  };

  return mapDateReferences(state, id => {
    const input: unknown = id;
    // js-yaml parses unquoted ISO dates as Date objects. Convert these before
    // browser storage copies their enumerable fields into an empty object.
    if (input instanceof Date && Number.isFinite(input.getTime())) {
      const isoDate = input.toISOString().split('T')[0];
      return getAlias(isoDate) ?? isoDate;
    }
    if (typeof input === 'number') return getAlias(String(input)) ?? id;
    return typeof input === 'string' ? (getAlias(input) ?? input) : id;
  });
}

export function findDateGroupIdCollision(state: ScheduleSpecState, range: DateRange): string | undefined {
  const groupIds = new Set(state.dates.groups.map(group => group.id).filter(isDateSelectorShape));
  if (groupIds.size === 0) return undefined;
  for (const dateRange of [state.dates.range, range]) {
    for (const id of dateIdsByIsoDate(dateRange).values()) {
      if (groupIds.has(id)) return id;
    }
  }
  return undefined;
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
