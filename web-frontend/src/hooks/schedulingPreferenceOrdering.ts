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

import { ShiftTypeRequirementsPreference, ShiftRequestPreference, Preference, AT_MOST_ONE_SHIFT_PER_DAY, SHIFT_TYPE_REQUIREMENT, SHIFT_REQUEST, SHIFT_TYPE_SUCCESSIONS, SHIFT_COUNT, SHIFT_AFFINITY } from '@/types/scheduling';
import { ALL } from '@/utils/keywords';
import { compareFirstIdByEntryOrder, getOrderedEntries, sortIdsByEntryOrder, sortPairsByFirstIdEntryOrder } from '@/utils/entityOrdering';
import { SchedulingState } from './schedulingState';

export type NullableShiftTypeRequirementsPreference = Omit<ShiftTypeRequirementsPreference, 'qualifiedPeople'> & {
  // Backend input accepts both null/missing and the reserved ALL selector for
  // all people. Frontend state normalizes the implicit form to [ALL].
  qualifiedPeople?: ShiftTypeRequirementsPreference['qualifiedPeople'] | null;
};

export function normalizeQualifiedPeopleForFrontend(
  qualifiedPeople: NullableShiftTypeRequirementsPreference['qualifiedPeople']
): string[] {
  // Normalize the backend's implicit all-people representation into the
  // frontend's explicit selector. Keeping [ALL] in client state is intentional;
  // the backend knows to interpret null as [ALL].
  return qualifiedPeople === null || qualifiedPeople === undefined ? [ALL] : qualifiedPeople;
}

export function normalizePreferenceOrder(pref: Preference, state: SchedulingState): Preference {
  const peopleEntries = getOrderedEntries(state.people);
  const shiftTypeEntries = getOrderedEntries(state.shiftTypes);
  const dateEntries = getOrderedEntries(state.dates);

  if (pref.type === SHIFT_TYPE_REQUIREMENT) {
    const requirementPref = pref as NullableShiftTypeRequirementsPreference;
    return {
      ...requirementPref,
      shiftType: sortIdsByEntryOrder(requirementPref.shiftType, shiftTypeEntries),
      shiftTypeCoefficients: sortPairsByFirstIdEntryOrder(requirementPref.shiftTypeCoefficients, shiftTypeEntries),
      qualifiedPeople: sortIdsByEntryOrder(normalizeQualifiedPeopleForFrontend(requirementPref.qualifiedPeople), peopleEntries),
      date: sortIdsByEntryOrder(requirementPref.date, dateEntries),
    };
  }
  if (pref.type === SHIFT_REQUEST) {
    return {
      ...pref,
      person: sortIdsByEntryOrder(pref.person, peopleEntries),
      date: sortIdsByEntryOrder(pref.date, dateEntries),
      shiftType: sortIdsByEntryOrder(pref.shiftType, shiftTypeEntries),
    };
  }
  if (pref.type === SHIFT_TYPE_SUCCESSIONS) {
    return {
      ...pref,
      person: sortIdsByEntryOrder(pref.person, peopleEntries),
      date: sortIdsByEntryOrder(pref.date, dateEntries),
    };
  }
  if (pref.type === SHIFT_COUNT) {
    return {
      ...pref,
      person: sortIdsByEntryOrder(pref.person, peopleEntries),
      countDates: sortIdsByEntryOrder(pref.countDates, dateEntries),
      countShiftTypes: sortIdsByEntryOrder(pref.countShiftTypes, shiftTypeEntries),
      countShiftTypeCoefficients: sortPairsByFirstIdEntryOrder(pref.countShiftTypeCoefficients, shiftTypeEntries),
    };
  }
  if (pref.type === SHIFT_AFFINITY) {
    return {
      ...pref,
      date: sortIdsByEntryOrder(pref.date, dateEntries),
      people1: sortIdsByEntryOrder(pref.people1, peopleEntries),
      people2: sortIdsByEntryOrder(pref.people2, peopleEntries),
      shiftTypes: sortIdsByEntryOrder(pref.shiftTypes, shiftTypeEntries),
    };
  }
  return pref;
}

export function sortPreferencesByType(preferences: Preference[]): Preference[] {
  const typeOrder = [AT_MOST_ONE_SHIFT_PER_DAY, SHIFT_TYPE_REQUIREMENT, SHIFT_REQUEST, SHIFT_TYPE_SUCCESSIONS, SHIFT_COUNT, SHIFT_AFFINITY];
  return [...preferences].sort((a, b) => typeOrder.indexOf(a.type) - typeOrder.indexOf(b.type));
}

export function sortShiftRequestsByEntityOrder(preferences: ShiftRequestPreference[], state: SchedulingState): ShiftRequestPreference[] {
  const peopleEntries = getOrderedEntries(state.people);
  const shiftTypeEntries = getOrderedEntries(state.shiftTypes);
  // Sort requests by person, then shift type, then weight; request dates are
  // normalized inside each request rather than used for list-level ordering.
  return [...preferences].sort((a, b) => {
    const personOrder = compareFirstIdByEntryOrder(a.person, b.person, peopleEntries);
    if (personOrder !== 0) return personOrder;
    const shiftTypeOrder = compareFirstIdByEntryOrder(a.shiftType, b.shiftType, shiftTypeEntries);
    if (shiftTypeOrder !== 0) return shiftTypeOrder;
    return a.weight - b.weight;
  });
}

// Normalize IDs within each preference, order shift requests by entities, then
// group all preferences by type for stable saved/exported state.
export function normalizePreferencesOrder(preferences: Preference[], state: SchedulingState): Preference[] {
  const normalizedPreferences = preferences.map(pref => normalizePreferenceOrder(pref, state));
  const sortedShiftRequests = sortShiftRequestsByEntityOrder(
    normalizedPreferences.filter((pref): pref is ShiftRequestPreference => pref.type === SHIFT_REQUEST),
    state
  );
  const otherPreferences = normalizedPreferences.filter(pref => pref.type !== SHIFT_REQUEST);

  return sortPreferencesByType([
    ...otherPreferences,
    ...sortedShiftRequests,
  ]);
}
