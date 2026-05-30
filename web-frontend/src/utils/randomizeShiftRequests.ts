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

// Developer utility for scattering concrete-date shift requests in exported scheduling snapshots.
import { SHIFT_REQUEST } from '@/types/scheduling';
import type { Group, Item, ShiftRequestPreference } from '@/types/scheduling';
import type { SchedulingState } from '@/hooks/useSchedulingData';
import { WEEKDAY, WEEKEND } from '@/utils/keywords';
import { TAIWAN_FREEDAY_GROUP_ID, TAIWAN_WORKDAY_GROUP_ID } from '@/utils/taiwanHolidays';

type Random = () => number;

// Return a shuffled copy so callers can randomize ordering without mutating source arrays.
function shuffled<T>(values: T[], random: Random): T[] {
  const result = [...values];
  // Fisher-Yates shuffle: swap each trailing element with a random earlier position.
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
  }
  return result;
}

// Report which imported holiday groups are absent so the UI can warn before using fallback groups.
export function getMissingPreferredScatterDateGroups(dateGroups: Group[]): string[] {
  const dateGroupIds = new Set(dateGroups.map(group => group.id));
  return [TAIWAN_WORKDAY_GROUP_ID, TAIWAN_FREEDAY_GROUP_ID].filter(id => !dateGroupIds.has(id));
}

function buildDateCategories(dateItems: Item[], dateGroups: Group[]): Map<string, string> {
  const missingPreferredGroups = getMissingPreferredScatterDateGroups(dateGroups);
  // Holiday-aware WORKDAY/FREEDAY groups are preferred. If either is unavailable,
  // classify the whole calendar consistently with generated WEEKDAY/WEEKEND groups.
  const [firstCategoryId, secondCategoryId] = missingPreferredGroups.length === 0
    ? [TAIWAN_WORKDAY_GROUP_ID, TAIWAN_FREEDAY_GROUP_ID]
    : [WEEKDAY, WEEKEND];
  // Sets make category membership checks cheap while scanning every concrete date.
  const firstCategory = new Set(dateGroups.find(group => group.id === firstCategoryId)?.members ?? []);
  const secondCategory = new Set(dateGroups.find(group => group.id === secondCategoryId)?.members ?? []);
  const categories = new Map<string, string>();

  dateItems.forEach(item => {
    const isFirstCategory = firstCategory.has(item.id);
    const isSecondCategory = secondCategory.has(item.id);
    // Every date must belong to exactly one side. Missing or overlapping membership
    // would make it impossible to preserve category counts reliably.
    if (isFirstCategory === isSecondCategory) {
      throw new Error(`Date "${item.id}" must belong to exactly one of ${firstCategoryId} or ${secondCategoryId}.`);
    }
    categories.set(item.id, isFirstCategory ? firstCategoryId : secondCategoryId);
  });

  return categories;
}

// Group adjacent requested date indexes into blocks so consecutive requests move together.
function findOccupiedRuns(occupiedIndexes: Set<number>): number[][] {
  const runs: number[][] = [];
  // Sorting turns arbitrary requested positions into calendar order.
  [...occupiedIndexes].sort((a, b) => a - b).forEach(index => {
    const lastRun = runs[runs.length - 1];
    // Extend the current block when this date immediately follows it.
    // Otherwise start a new independently movable block.
    if (lastRun && lastRun[lastRun.length - 1] === index - 1) {
      lastRun.push(index);
    } else {
      runs.push([index]);
    }
  });
  return runs;
}

function movePersonRequests(
  requests: ShiftRequestPreference[],
  dateItems: Item[],
  dateCategories: Map<string, string>,
  random: Random
): ShiftRequestPreference[] {
  // Convert date IDs to positions because adjacency is defined by calendar order.
  const dateIndexById = new Map(dateItems.map((item, index) => [item.id, index]));
  // Multiple request records can target the same date with different shift types or weights.
  // A Set collapses those duplicates because each occupied date should move only once.
  const occupiedIndexes = new Set(
    requests.flatMap(request => request.date.map(dateId => dateIndexById.get(dateId)!))
  );
  // Randomize block processing order so the same early calendar blocks do not always
  // get first choice of destinations.
  const runs = shuffled(findOccupiedRuns(occupiedIndexes), random);
  // Track newly chosen destinations. Source positions are deliberately not reserved,
  // allowing blocks to move into one another's old locations.
  const allocatedIndexes = new Set<number>();
  // Record the final date translation once per occupied source date. All request
  // records referring to that date will receive the same moved destination.
  const movedDateByOriginalDate = new Map<string, string>();

  runs.forEach(run => {
    // Count categories across the whole block. Their order may change after moving:
    // [WORKDAY, FREEDAY] is allowed to become [FREEDAY, WORKDAY].
    const categoryCounts = new Map<string, number>();
    run.forEach(index => {
      const category = dateCategories.get(dateItems[index].id)!;
      categoryCounts.set(category, (categoryCounts.get(category) ?? 0) + 1);
    });

    // Find consecutive destination slots with the same workday/freeday totals.
    // Old source positions remain available so blocks can swap places.
    const candidateStarts = dateItems
      // Try every date as a potential first destination slot.
      .map((_, index) => index)
      // Exclude starts where the block would extend past the calendar end.
      .filter(start => start + run.length <= dateItems.length)
      .filter(start => {
        const candidateCategoryCounts = new Map<string, number>();
        for (let offset = 0; offset < run.length; offset += 1) {
          // A previously placed block already owns this destination slot.
          if (allocatedIndexes.has(start + offset)) return false;
          const category = dateCategories.get(dateItems[start + offset].id)!;
          candidateCategoryCounts.set(category, (candidateCategoryCounts.get(category) ?? 0) + 1);
        }
        // Keep only destinations with the original block's workday/freeday totals.
        return [...categoryCounts].every(([category, count]) => candidateCategoryCounts.get(category) === count);
      });
    // Prefer an actual move. Keep the original location only when no alternative fits.
    const alternativeStarts = candidateStarts.filter(start => start !== run[0]);
    const startsToChooseFrom = alternativeStarts.length > 0 ? alternativeStarts : candidateStarts;
    // Greedy placement keeps the algorithm simple. If no free destination exists,
    // keep the original position when possible rather than reshuffling earlier choices.
    const targetStart = shuffled(startsToChooseFrom, random)[0];
    if (targetStart === undefined) {
      throw new Error('Unable to scatter shift requests without overlapping consecutive runs.');
    }

    run.forEach((originalIndex, offset) => {
      // Reserve the destination and store the source-to-destination translation.
      allocatedIndexes.add(targetStart + offset);
      movedDateByOriginalDate.set(dateItems[originalIndex].id, dateItems[targetStart + offset].id);
    });
  });

  // Rewrite copies of the original requests. Sorting keeps YAML dates in calendar order.
  return requests.map(request => ({
    ...request,
    date: request.date
      .map(dateId => movedDateByOriginalDate.get(dateId) ?? dateId)
      .sort((a, b) => dateIndexById.get(a)! - dateIndexById.get(b)!)
  }));
}

export function randomizeConcreteDateShiftRequests(
  state: SchedulingState,
  dateItems: Item[],
  dateGroups: Group[],
  random: Random = Math.random
): SchedulingState {
  // These sets distinguish concrete date and person items from group references.
  const dateItemIds = new Set(dateItems.map(item => item.id));
  const peopleItemIds = new Set(state.people.items.map(item => item.id));
  const dateCategories = buildDateCategories(dateItems, dateGroups);
  // Scatter each person independently so one person's requests never affect another's.
  const movableByPerson = new Map<string, ShiftRequestPreference[]>();

  state.preferences.forEach(pref => {
    // Only scatter requests for one concrete person and concrete dates. Leave group
    // requests such as ALL, WORKDAY, or a people team exactly as written.
    if (
      pref.type === SHIFT_REQUEST &&
      pref.person.length === 1 &&
      peopleItemIds.has(pref.person[0]) &&
      pref.date.every(dateId => dateItemIds.has(dateId))
    ) {
      const requests = movableByPerson.get(pref.person[0]) ?? [];
      requests.push(pref);
      movableByPerson.set(pref.person[0], requests);
    }
  });

  // Keep a lookup from each original request object to its rewritten copy. This lets
  // the final pass preserve preference ordering and leave unrelated records untouched.
  const randomizedRequests = new Map<ShiftRequestPreference, ShiftRequestPreference>();
  movableByPerson.forEach(requests => {
    movePersonRequests(requests, dateItems, dateCategories, random).forEach((request, index) => {
      randomizedRequests.set(requests[index], request);
    });
  });

  // Return an exported snapshot copy. The live scheduling state is never mutated.
  return {
    ...state,
    preferences: state.preferences.map(pref =>
      pref.type === SHIFT_REQUEST ? randomizedRequests.get(pref) ?? pref : pref
    )
  };
}
