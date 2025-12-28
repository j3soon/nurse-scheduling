/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
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

import { DateRange } from "@/types/scheduling";
import { ERROR_SHOULD_NOT_HAPPEN } from "@/constants/errors";

export function dateStrToDate(dateStr: string, dateRange: DateRange): Date {
  // Parse the item.id back to a Date, inferring year/month if needed.
  // Use dateRange to infer missing year/month if needed.
  if (dateRange.startDate === undefined) {
    console.error(`dateRange.startDate is undefined. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return new Date();
  }
  // If id is YYYY-MM-DD, parse directly.
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return new Date(dateStr);
  }
  // If id is MM-DD, infer year from dateRange.startDate
  if (/^\d{2}-\d{2}$/.test(dateStr)) {
    const yyyy = dateRange.startDate!.getFullYear().toString().padStart(4, '0');
    const [mm, dd] = dateStr.split('-');
    return new Date(`${yyyy}-${mm}-${dd}`);
  }
  // If id is DD, infer month and year from dateRange.startDate
  if (/^\d{2}$/.test(dateStr)) {
    const yyyy = dateRange.startDate!.getFullYear().toString().padStart(4, '0');
    const mm = (dateRange.startDate!.getMonth() + 1).toString().padStart(2, '0');
    const dd = dateStr;
    return new Date(`${yyyy}-${mm}-${dd}`);
  }
  console.error(`Invalid date string: ${dateStr}. ${ERROR_SHOULD_NOT_HAPPEN}`);
  return new Date();
}
