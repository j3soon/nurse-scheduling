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

import { DateRange, Group, Item } from '@/types/scheduling';
import { dateStrToDate } from '@/utils/dateParsing';

// Useful references:
// * [DGPA Work Calendar](https://www.dgpa.gov.tw/informationlist?uid=30)
// * [MODA Open Data](https://data.gov.tw/dataset/14718)
// * [Holidays Python Package (Taiwan)](https://github.com/vacanza/holidays/blob/dev/holidays/countries/taiwan.py)

export const TAIWAN_WORKDAY_GROUP_ID = 'WORKDAY';
export const TAIWAN_FREEDAY_GROUP_ID = 'FREEDAY';
export const TAIWAN_HOLIDAY_SUPPORTED_START = '2023-01-01';
export const TAIWAN_HOLIDAY_SUPPORTED_END = '2025-12-31';

type TaiwanSpecialDateInfo = [string, string, boolean];

const SPECIAL_DATE_INFO: TaiwanSpecialDateInfo[] = [
  // 2023
  ['2023-01-01', '開國紀念日 (2023-01-02 補假)', true],
  ['2023-01-02', '補假 (2023-01-01 開國紀念日)', true],
  ['2023-01-07', '補行上班 (2023-01-20 小年夜)', false],
  ['2023-01-20', '小年夜 (2023-01-07 補行上班)', true],
  ['2023-01-21', '農曆除夕 (2023-01-25 補假)', true],
  ['2023-01-22', '春節 (2023-01-26 補假)', true],
  ['2023-01-23', '春節', true],
  ['2023-01-24', '春節', true],
  ['2023-01-25', '補假 (2023-01-21 農曆除夕)', true],
  ['2023-01-26', '補假 (2023-01-22 春節)', true],
  ['2023-01-27', '調整放假 (2023-02-04 補行上班)', true],
  ['2023-02-04', '補行上班 (2023-01-27 調整放假)', false],
  ['2023-02-18', '補行上班 (2023-02-27 調整放假)', false],
  ['2023-02-27', '調整放假 (2023-02-18 補行上班)', true],
  ['2023-02-28', '和平紀念日', true],
  ['2023-03-25', '補行上班 (2023-04-03 調整放假)', false],
  ['2023-04-03', '調整放假 (2023-03-25 補行上班)', true],
  ['2023-04-04', '兒童節', true],
  ['2023-04-05', '民族掃墓節', true],
  ['2023-06-17', '補行上班 (2023-06-23 調整放假)', false],
  ['2023-06-22', '端午節', true],
  ['2023-06-23', '調整放假 (2023-06-17 補行上班)', true],
  ['2023-09-23', '補行上班 (2023-10-09 調整放假)', false],
  ['2023-09-29', '中秋節', true],
  ['2023-10-09', '調整放假 (2023-09-23 補行上班)', true],
  ['2023-10-10', '國慶日', true],
  // 2024
  ['2024-01-01', '開國紀念日', true],
  ['2024-02-08', '小年夜 (2024-02-17 補行上班)', true],
  ['2024-02-09', '農曆除夕', true],
  ['2024-02-10', '春節 (2024-02-13 補假)', true],
  ['2024-02-11', '春節 (2024-02-14 補假)', true],
  ['2024-02-12', '春節', true],
  ['2024-02-13', '補假 (2024-02-10 春節)', true],
  ['2024-02-14', '補假 (2024-02-11 春節)', true],
  ['2024-02-17', '補行上班 (2024-02-08 小年夜)', false],
  ['2024-02-28', '和平紀念日', true],
  ['2024-04-04', '兒童節及民族掃墓節', true],
  ['2024-04-05', '補假 (2024-04-04 兒童節及民族掃墓節)', true],
  ['2024-06-10', '端午節', true],
  ['2024-09-17', '中秋節', true],
  ['2024-10-10', '國慶日', true],
  // 2025
  ['2025-01-01', '開國紀念日', true],
  ['2025-01-27', '小年夜 (2025-02-08 補行上班)', true],
  ['2025-01-28', '農曆除夕', true],
  ['2025-01-29', '春節', true],
  ['2025-01-30', '春節', true],
  ['2025-01-31', '春節', true],
  ['2025-02-08', '補行上班 (2025-01-27 小年夜)', false],
  ['2025-02-28', '和平紀念日', true],
  ['2025-04-03', '補假 (2025-04-04 兒童節及民族掃墓節)', true],
  ['2025-04-04', '兒童節及民族掃墓節', true],
  ['2025-05-30', '補假 (2025-05-31 端午節)', true],
  ['2025-05-31', '端午節', true],
  ['2025-09-28', '孔子誕辰紀念日', true],
  ['2025-09-29', '補假 (2025-09-28 孔子誕辰紀念日)', true],
  ['2025-10-06', '中秋節', true],
  ['2025-10-10', '國慶日', true],
  ['2025-10-24', '補假 (2025-10-25 臺灣光復暨金門古寧頭大捷紀念日)', true],
  ['2025-10-25', '臺灣光復暨金門古寧頭大捷紀念日', true],
  ['2025-12-25', '行憲紀念日', true],
  // 2026
  ['2026-01-01', '開國紀念日', true],
  ['2026-02-15', '小年夜', true],
  ['2026-02-16', '農曆除夕', true],
  ['2026-02-17', '春節', true],
  ['2026-02-18', '春節', true],
  ['2026-02-19', '春節', true],
  ['2026-02-20', '補假 (2026-02-15 小年夜)', true],
  ['2026-02-27', '補假 (2026-02-28 和平紀念日)', true],
  ['2026-02-28', '和平紀念日', true],
  ['2026-04-03', '補假 (2026-04-04 兒童節)', true],
  ['2026-04-04', '兒童節', true],
  ['2026-04-05', '清明節', true],
  ['2026-04-06', '補假 (2026-04-04 兒童節)', true],
  ['2026-05-01', '勞動節', true],
  ['2026-06-19', '端午節', true],
  ['2026-09-25', '中秋節', true],
  ['2026-09-28', '孔子誕辰紀念日/教師節', true],
  ['2026-10-09', '補假 (2026-10-10 國慶日)', true],
  ['2026-10-10', '國慶日', true],
  ['2026-10-25', '臺灣光復暨金門古寧頭大捷紀念日', true],
  ['2026-10-26', '補假 (2026-10-25 臺灣光復暨金門古寧頭大捷紀念日)', true],
  ['2026-12-25', '行憲紀念日', true],
];

const SPECIAL_DATE_LOOKUP = new Map(
  SPECIAL_DATE_INFO.map(([date, reason, isFreeday]) => [date, { reason, isFreeday }])
);

function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export function getTaiwanHolidaySupportLabel(): string {
  return `${TAIWAN_HOLIDAY_SUPPORTED_START} to ${TAIWAN_HOLIDAY_SUPPORTED_END}`;
}

export function isTaiwanHolidayRangeSupported(dateRange: DateRange): boolean {
  if (!dateRange.startDate || !dateRange.endDate) {
    return false;
  }

  const start = formatDate(dateRange.startDate);
  const end = formatDate(dateRange.endDate);
  return start >= TAIWAN_HOLIDAY_SUPPORTED_START && end <= TAIWAN_HOLIDAY_SUPPORTED_END;
}

function isTaiwanFreeday(date: Date): boolean {
  const dateKey = formatDate(date);
  const special = SPECIAL_DATE_LOOKUP.get(dateKey);
  if (special !== undefined) {
    return special.isFreeday;
  }

  return date.getDay() === 0 || date.getDay() === 6;
}

function includesDate(dateRange: DateRange, dateKey: string): boolean {
  if (!dateRange.startDate || !dateRange.endDate) {
    return false;
  }

  const start = formatDate(dateRange.startDate);
  const end = formatDate(dateRange.endDate);
  return start <= dateKey && dateKey <= end;
}

export function buildTaiwanHolidayGroups(items: Item[], dateRange: DateRange): Group[] {
  if (!dateRange.startDate || !dateRange.endDate || !isTaiwanHolidayRangeSupported(dateRange)) {
    return [];
  }

  const workdayMembers: string[] = [];
  const freedayMembers: string[] = [];

  for (const item of items) {
    const date = dateStrToDate(item.id, dateRange);
    if (isTaiwanFreeday(date)) {
      freedayMembers.push(item.id);
    } else {
      workdayMembers.push(item.id);
    }
  }

  return [
    {
      id: TAIWAN_WORKDAY_GROUP_ID,
      description: 'Taiwan workdays imported from the current holiday calendar',
      members: workdayMembers,
    },
    {
      id: TAIWAN_FREEDAY_GROUP_ID,
      description: 'Taiwan freedays imported from the current holiday calendar',
      members: freedayMembers,
    },
  ];
}

export function includesUnimportedTaiwanLaborDay(dateRange: DateRange): boolean {
  return ['2023-05-01', '2024-05-01'].some(dateKey => includesDate(dateRange, dateKey));
}
