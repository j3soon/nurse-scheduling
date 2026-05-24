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

// This test is mostly AI generated.

import { restoreScrollPosition, saveScrollPosition } from '@/utils/scrolling';

describe('scrolling utilities', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
  });

  it('saves and restores scroll position through requestAnimationFrame', () => {
    Object.defineProperty(window, 'scrollY', {
      configurable: true,
      writable: true,
      value: 240,
    });
    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);

    saveScrollPosition();
    restoreScrollPosition();

    expect(scrollToSpy).toHaveBeenCalledWith({ top: 240, behavior: 'instant' });
  });

  it('logs an error when restore is called without a saved position', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    restoreScrollPosition();

    expect(errorSpy).toHaveBeenCalled();
  });
});
