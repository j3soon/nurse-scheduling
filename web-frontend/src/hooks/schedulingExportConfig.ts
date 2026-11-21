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

import { ExportConfig, ExportDefaults } from '@/types/scheduling';
import { getOrderedEntries, sortIdsByEntryOrder, sortPairsByFirstIdEntryOrder } from '@/utils/entityOrdering';
import { ScheduleSpecState } from './scheduleSpecState';

export function normalizeExportFormattingOrder(formatting: ExportConfig['formatting'], state: ScheduleSpecState) {
  if (!formatting) return formatting;

  const peopleEntries = getOrderedEntries(state.people);
  const shiftTypeEntries = getOrderedEntries(state.shiftTypes);
  const dateEntries = getOrderedEntries(state.dates);

  return formatting.map(rule => {
    let updatedRule = { ...rule };
    if ('people' in updatedRule) {
      updatedRule = { ...updatedRule, people: sortIdsByEntryOrder(updatedRule.people, peopleEntries) };
    }
    if ('dates' in updatedRule) {
      updatedRule = { ...updatedRule, dates: sortIdsByEntryOrder(updatedRule.dates, dateEntries) };
    }
    if ('shiftTypes' in updatedRule) {
      updatedRule = { ...updatedRule, shiftTypes: sortIdsByEntryOrder(updatedRule.shiftTypes, shiftTypeEntries) };
    }
    return updatedRule;
  });
}

export function normalizeExportExtraColumnsOrder(extraColumns: ExportConfig['extraColumns'], state: ScheduleSpecState) {
  if (!extraColumns) return extraColumns;

  const shiftTypeEntries = getOrderedEntries(state.shiftTypes);
  const dateEntries = getOrderedEntries(state.dates);
  return extraColumns.map(rule => rule.type === 'defaults' ? rule : ({
    ...rule,
    countShiftTypes: sortIdsByEntryOrder(rule.countShiftTypes, shiftTypeEntries),
    countShiftTypeCoefficients: sortPairsByFirstIdEntryOrder(rule.countShiftTypeCoefficients, shiftTypeEntries),
    countDates: sortIdsByEntryOrder(rule.countDates, dateEntries),
  }));
}

export function normalizeExportExtraRowsOrder(extraRows: ExportConfig['extraRows'], state: ScheduleSpecState) {
  if (!extraRows) return extraRows;

  const peopleEntries = getOrderedEntries(state.people);
  const shiftTypeEntries = getOrderedEntries(state.shiftTypes);
  return extraRows.map(rule => rule.type === 'defaults' ? rule : ({
    ...rule,
    countShiftTypes: sortIdsByEntryOrder(rule.countShiftTypes, shiftTypeEntries),
    countPeople: sortIdsByEntryOrder(rule.countPeople, peopleEntries),
  }));
}

export function normalizeExportConfigOrder(exportConfig: ExportConfig | undefined, state: ScheduleSpecState) {
  if (!exportConfig) return exportConfig;

  return {
    ...exportConfig,
    formatting: normalizeExportFormattingOrder(exportConfig.formatting, state),
    extraColumns: normalizeExportExtraColumnsOrder(exportConfig.extraColumns, state),
    extraRows: normalizeExportExtraRowsOrder(exportConfig.extraRows, state),
  };
}

export const defaultExportEntry: ExportDefaults = { type: 'defaults' };

export const defaultExportConfig: ExportConfig = {
  formatting: [defaultExportEntry],
  extraColumns: [defaultExportEntry],
  extraRows: [defaultExportEntry],
};

export function usesOnlyExportDefaults(config: ExportConfig | undefined) {
  return config && (['formatting', 'extraColumns', 'extraRows'] as const).every(section =>
    config[section]?.length === 1 && config[section][0].type === 'defaults'
  );
}
