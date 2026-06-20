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

export const STORAGE_KEY = 'nurse-scheduling-data';
export const WORKER_NAMESPACE_KEY = '__PLAYWRIGHT_WORKER_NAMESPACE__';

// Constants for infinity value handling in localStorage
// JSON.stringify converts Infinity to null and JSON.parse doesn't handle infinity properly
// These placeholders allow us to safely store and retrieve infinity values
export const INFINITY_PLACEHOLDER = '__INFINITY__';
export const NEGATIVE_INFINITY_PLACEHOLDER = '__NEGATIVE_INFINITY__';
export const WORKDAY = 'WORKDAY';
export const FREEDAY = 'FREEDAY';
export const DEFAULT_SEPARATOR_COLOR = '#000000';
