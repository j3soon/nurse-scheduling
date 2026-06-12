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

import { Group, Item, ShiftCountTypeCoefficient } from '@/types/scheduling';

export type DraftShiftCountTypeCoefficient = [string, number | string];

export interface ShiftCountTypeCoefficientValidation {
  coefficients: ShiftCountTypeCoefficient[];
  errorsById: Record<string, string>;
  overlapError?: string;
}

export function getCoefficientForShiftType(
  coefficients: DraftShiftCountTypeCoefficient[],
  shiftTypeId: string
): number | string {
  return coefficients.find(([id]) => id === shiftTypeId)?.[1] ?? 1;
}

export function syncCoefficientPairs(
  selectedShiftTypeIds: string[],
  coefficients: DraftShiftCountTypeCoefficient[]
): DraftShiftCountTypeCoefficient[] {
  return selectedShiftTypeIds.map(id => [id, getCoefficientForShiftType(coefficients, id)]);
}

export function updateCoefficientPair(
  selectedShiftTypeIds: string[],
  coefficients: DraftShiftCountTypeCoefficient[],
  shiftTypeId: string,
  coefficient: number | string
): DraftShiftCountTypeCoefficient[] {
  return syncCoefficientPairs(selectedShiftTypeIds, [
    ...coefficients.filter(([id]) => id !== shiftTypeId),
    [shiftTypeId, coefficient],
  ]);
}

function getCoefficientOverlapError(
  coefficientPairs: ShiftCountTypeCoefficient[],
  shiftTypeData: { items: Item[]; groups: Group[] }
): string | undefined {
  const expandedShiftTypeIdsById = new Map([
    ...shiftTypeData.items.map(shiftType => [shiftType.id, [shiftType.id]] as const),
    ...shiftTypeData.groups.map(group => [group.id, [...new Set(group.members)]] as const),
  ]);

  const sourceShiftTypeIdByExpandedId = new Map<string, string>();
  for (const [shiftTypeId] of coefficientPairs) {
    for (const expandedShiftTypeId of expandedShiftTypeIdsById.get(shiftTypeId) ?? []) {
      const existingSourceShiftTypeId = sourceShiftTypeIdByExpandedId.get(expandedShiftTypeId);
      if (existingSourceShiftTypeId !== undefined) {
        return `Shift type coefficients overlap: ${existingSourceShiftTypeId}, ${shiftTypeId} include ${expandedShiftTypeId}`;
      }
      sourceShiftTypeIdByExpandedId.set(expandedShiftTypeId, shiftTypeId);
    }
  }

  return undefined;
}

export function validateCoefficientPairs(
  selectedShiftTypeIds: string[],
  coefficients: DraftShiftCountTypeCoefficient[],
  shiftTypeData: { items: Item[]; groups: Group[] }
): ShiftCountTypeCoefficientValidation {
  const syncedCoefficients = syncCoefficientPairs(selectedShiftTypeIds, coefficients);
  const errorsById: Record<string, string> = {};

  for (const [shiftTypeId, coefficient] of syncedCoefficients) {
    if (typeof coefficient !== 'number' || !Number.isInteger(coefficient) || coefficient < 1) {
      errorsById[shiftTypeId] = `Coefficient for ${shiftTypeId} must be an integer of at least 1`;
    }
  }

  if (Object.keys(errorsById).length > 0) {
    return { coefficients: [], errorsById };
  }

  const normalizedCoefficients = syncedCoefficients.filter(
    ([, coefficient]) => coefficient !== 1
  ) as ShiftCountTypeCoefficient[];

  return {
    coefficients: normalizedCoefficients,
    errorsById,
    overlapError: getCoefficientOverlapError(normalizedCoefficients, shiftTypeData),
  };
}
