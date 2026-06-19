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

import { Item, Group, DateRange, Preference, AT_MOST_ONE_SHIFT_PER_DAY, ExportConfig } from '@/types/scheduling';
import { API_VERSION } from '@/utils/keywords';
import { FREEDAY, WORKDAY } from './schedulingConstants';

export interface SchedulingState {
  apiVersion: string | number;
  description: string;
  dates: { range: DateRange, items: Item[]; groups: Group[] };
  people: { items: Item[]; groups: Group[] };
  shiftTypes: { items: Item[]; groups: Group[] };
  preferences: Preference[];
  export?: ExportConfig;
}

export function createDefaultPeople() {
  return {
    items: Array.from({ length: 10 }, (_, index) => ({
      id: `Person ${index + 1}`,
      description: '',
      history: [] // Start with empty history
    })),
    groups: [
      { id: 'Group 1', members: ['Person 1', 'Person 2'], description: '' },
      { id: 'Group 2', members: ['Person 2', 'Person 3', 'Person 4'], description: '' },
      { id: 'Group 3', members: ['Person 3', 'Person 4', 'Person 5', 'Person 6'], description: '' },
      { id: 'Group 4', members: ['Person 4', 'Person 5', 'Person 6', 'Person 7', 'Person 8'], description: '' },
      { id: 'Group 5', members: ['Person 5', 'Person 6', 'Person 7', 'Person 8', 'Person 9', 'Person 10'], description: '' },
    ]
  };
}

export function createDefaultShiftTypes() {
  return {
    items: [
      { id: 'D', description: 'Day (All Levels)' },
      { id: 'D+', description: 'Day (Senior Only)' },
      { id: 'E', description: 'Evening (All Levels)' },
      { id: 'E+', description: 'Evening (Senior Only)' },
      { id: 'N', description: 'Night (All Levels)' },
      { id: 'N+', description: 'Night (Senior Only)' },
      { id: 'A', description: 'Admin (All Levels)' },
      { id: 'A+', description: 'Admin (Senior Only)' },
      { id: 'A-', description: 'Admin (Assistant Only)' },
    ],
    groups: [
      { id: 'Day', members: ['D', 'D+'], description: 'All day shift types' },
      { id: 'Evening', members: ['E', 'E+'], description: 'All evening shift types' },
      { id: 'Night', members: ['N', 'N+'], description: 'All night shift types' },
      { id: 'Administrative', members: ['A', 'A+', 'A-'], description: 'All administrative shift types' },
    ]
  };
}

export function createDefaultState(): SchedulingState {
  const shiftTypes = createDefaultShiftTypes();
  const dates = {
    range: { startDate: undefined, endDate: undefined },
    items: [],
    groups: [
      {
        id: WORKDAY,
        members: [],
        description: 'Workdays'
      },
      {
        id: FREEDAY,
        members: [],
        description: 'Freedays'
      }
    ]
  };
  return {
    apiVersion: API_VERSION,
    description: '',
    dates,
    people: createDefaultPeople(),
    shiftTypes,
    preferences: [
      {
        type: AT_MOST_ONE_SHIFT_PER_DAY
      }
    ]
  };
}
