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

import { ERROR_SHOULD_NOT_HAPPEN } from "@/constants/errors";

// Utility functions for saving and restoring scroll position

let savedScrollPosition: number | null = null;

/**
 * Saves the current scroll position to be restored later.
 * Typically called when opening an edit form.
 */
export function saveScrollPosition(): void {
  savedScrollPosition = window.scrollY;
}

/**
 * Restores the previously saved scroll position.
 * Typically called when closing an edit form (cancel or save).
 * Uses requestAnimationFrame to defer scrolling until after React has updated
 * the DOM (i.e., after the form has been hidden), ensuring the scroll position
 * is correct. Don't use `setTimeout` with 0 ms, as it will cause flickering.
 */
export function restoreScrollPosition(): void {
  if (savedScrollPosition !== null) {
    const scrollTo = savedScrollPosition;
    savedScrollPosition = null;
    // Defer scroll until after DOM updates (next paint cycle)
    requestAnimationFrame(() => {
      window.scrollTo({ top: scrollTo, behavior: 'instant' });
    });
  } else {
    console.error(`savedScrollPosition is null. ${ERROR_SHOULD_NOT_HAPPEN}.`);
  }
}
