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

import { Item, Group, DateRange, Preference, ExportConfig } from '@/types/scheduling';
import { API_VERSION } from '@/utils/keywords';

export interface SchedulingState {
  apiVersion: string | number;
  description: string;
  dates: { range: DateRange, items: Item[]; groups: Group[] };
  people: { items: Item[]; groups: Group[] };
  shiftTypes: { items: Item[]; groups: Group[] };
  preferences: Preference[];
  export?: ExportConfig;
}

export function createDefaultState(): SchedulingState {
  return {
    apiVersion: API_VERSION,
    description: '',
    dates: {
      range: { startDate: undefined, endDate: undefined },
      items: [],
      groups: [],
    },
    people: { items: [], groups: [] },
    shiftTypes: { items: [], groups: [] },
    preferences: [],
  };
}
