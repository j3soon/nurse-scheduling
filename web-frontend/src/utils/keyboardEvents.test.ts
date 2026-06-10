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

import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { isImeCompositionKeyEvent } from '@/utils/keyboardEvents';

function keyboardEventWithKeyCode(keyCode: number): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key: 'Enter' });
  Object.defineProperty(event, 'keyCode', { value: keyCode });
  return event;
}

describe('isImeCompositionKeyEvent', () => {
  it('detects native composing key events', () => {
    const event = new KeyboardEvent('keydown', { key: 'Enter', isComposing: true });

    expect(isImeCompositionKeyEvent(event)).toBe(true);
  });

  it('detects IME process key events by keyCode fallback', () => {
    expect(isImeCompositionKeyEvent(keyboardEventWithKeyCode(229))).toBe(true);
  });

  it('detects composing React keyboard events', () => {
    const nativeEvent = new KeyboardEvent('keydown', { key: 'Enter', isComposing: true });
    const reactEvent = { nativeEvent } as ReactKeyboardEvent<HTMLInputElement>;

    expect(isImeCompositionKeyEvent(reactEvent)).toBe(true);
  });

  it('does not flag normal key events', () => {
    expect(isImeCompositionKeyEvent(new KeyboardEvent('keydown', { key: 'Enter' }))).toBe(false);
  });
});
