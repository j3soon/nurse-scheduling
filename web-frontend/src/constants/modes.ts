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

// The states for each management page.
export enum Mode {
  NORMAL = 'NORMAL',
  ADDING = 'ADDING',
  EDITING = 'EDITING',
  INLINE_EDITING = 'INLINE_EDITING',
  DATE_RANGE_EDITING = 'DATE_RANGE_EDITING'
}
