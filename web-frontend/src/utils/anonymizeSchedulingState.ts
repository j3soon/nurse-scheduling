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

// Utility functions for anonymizing people identifiers in exported scheduling state.
import {
  SHIFT_AFFINITY,
  SHIFT_COUNT,
  SHIFT_REQUEST,
  SHIFT_TYPE_REQUIREMENT,
  SHIFT_TYPE_SUCCESSIONS
} from '@/types/scheduling';
import type { Preference } from '@/types/scheduling';
import type { SchedulingState } from '@/hooks/useSchedulingData';

export interface PeopleAnonymizationOptions {
  anonymizePeopleItems: boolean;
  anonymizePeopleGroups: boolean;
}

function buildIdMap(ids: string[], prefix: string, usedIds: Set<string>): Map<string, string> {
  const idMap = new Map<string, string>();
  let nextIndex = 1;

  ids.forEach(id => {
    let anonymizedId = `${prefix}${nextIndex}`;
    while (usedIds.has(anonymizedId)) {
      nextIndex += 1;
      anonymizedId = `${prefix}${nextIndex}`;
    }
    idMap.set(id, anonymizedId);
    usedIds.add(anonymizedId);
    nextIndex += 1;
  });

  return idMap;
}

function anonymizePreference(pref: Preference, anonymizeIds: (ids: string[]) => string[]): Preference {
  if (pref.type === SHIFT_TYPE_REQUIREMENT) {
    return { ...pref, qualifiedPeople: anonymizeIds(pref.qualifiedPeople) };
  }
  if (pref.type === SHIFT_REQUEST || pref.type === SHIFT_TYPE_SUCCESSIONS || pref.type === SHIFT_COUNT) {
    return { ...pref, person: anonymizeIds(pref.person) };
  }
  if (pref.type === SHIFT_AFFINITY) {
    return {
      ...pref,
      people1: anonymizeIds(pref.people1),
      people2: anonymizeIds(pref.people2)
    };
  }
  return pref;
}

export function anonymizePeopleInState(
  state: SchedulingState,
  options: PeopleAnonymizationOptions
): SchedulingState {
  const retainedIds = new Set<string>();
  if (!options.anonymizePeopleItems) {
    state.people.items.forEach(item => retainedIds.add(item.id));
  }
  if (!options.anonymizePeopleGroups) {
    state.people.groups.forEach(group => retainedIds.add(group.id));
  }

  const itemIdMap = options.anonymizePeopleItems
    ? buildIdMap(state.people.items.map(item => item.id), 'P', retainedIds)
    : new Map<string, string>();
  const groupIdMap = options.anonymizePeopleGroups
    ? buildIdMap(state.people.groups.map(group => group.id), 'G', retainedIds)
    : new Map<string, string>();
  const idMap = new Map([...itemIdMap, ...groupIdMap]);
  const anonymizeId = (id: string) => idMap.get(id) ?? id;
  const anonymizeIds = (ids: string[]) => ids.map(anonymizeId);

  return {
    ...state,
    people: {
      ...state.people,
      items: state.people.items.map(item => ({ ...item, id: anonymizeId(item.id) })),
      groups: state.people.groups.map(group => ({
        ...group,
        id: anonymizeId(group.id),
        members: anonymizeIds(group.members)
      }))
    },
    preferences: state.preferences.map(pref => anonymizePreference(pref, anonymizeIds)),
    ...(state.export
      ? {
          export: {
            ...state.export,
            formatting: state.export.formatting?.map(rule =>
              'people' in rule ? { ...rule, people: anonymizeIds(rule.people) } : rule
            ),
            extraRows: state.export.extraRows?.map(rule => ({
              ...rule,
              countPeople: anonymizeIds(rule.countPeople)
            }))
          }
        }
      : {})
  };
}
