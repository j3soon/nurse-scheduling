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

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import Navigation from '@/components/Navigation';
import {
  UnsavedEditingStateProvider,
  useUnsavedEditingState,
} from '@/utils/unsavedEditingState';

const mockPush = vi.hoisted(() => vi.fn());
const mockPrefetch = vi.hoisted(() => vi.fn());
const mockUsePathname = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, prefetch: mockPrefetch }),
  usePathname: () => mockUsePathname(),
}));

function TestTabSwitchWarning() {
  const { setTabSwitchWarningActive, clearTabSwitchWarningActive } = useUnsavedEditingState();

  useEffect(() => {
    setTabSwitchWarningActive();

    return () => {
      clearTabSwitchWarningActive();
    };
  }, [clearTabSwitchWarningActive, setTabSwitchWarningActive]);

  return null;
}

function renderNavigation({ tabSwitchWarningActive = false } = {}) {
  return render(
    <UnsavedEditingStateProvider>
      {tabSwitchWarningActive && <TestTabSwitchWarning />}
      <Navigation />
    </UnsavedEditingStateProvider>
  );
}

describe('Navigation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockPush.mockReset();
    mockPrefetch.mockReset();
    mockUsePathname.mockReturnValue('/people');
    vi.spyOn(window, 'scrollBy').mockImplementation(() => undefined);
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('prefetches all inactive tabs after render', () => {
    renderNavigation();

    expect(mockPrefetch).toHaveBeenCalledWith('/');
    expect(mockPrefetch).toHaveBeenCalledWith('/dates');
    expect(mockPrefetch).toHaveBeenCalledWith('/shift-types');
    expect(mockPrefetch).toHaveBeenCalledWith('/optimize-and-export');
    expect(mockPrefetch).not.toHaveBeenCalledWith('/people');
  });

  it('navigates when a tab button is clicked', async () => {
    const user = userEvent.setup();

    renderNavigation();

    await user.click(screen.getByRole('button', { name: '5. Shift Requests' }));

    expect(mockPush).toHaveBeenCalledWith('/shift-requests');
  });

  it('supports number-key shortcut navigation when no input is focused', () => {
    renderNavigation();

    fireEvent.keyDown(document, { key: '5' });

    expect(mockPush).toHaveBeenCalledWith('/shift-requests');
  });

  it('does not use number shortcuts while an input is focused', () => {
    renderNavigation();

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(document, { key: '5' });

    expect(mockPush).not.toHaveBeenCalled();
    input.blur();
    input.remove();
  });

  it('navigates with arrow keys and scroll shortcuts', () => {
    renderNavigation();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    expect(mockPush).toHaveBeenCalledWith('/dates');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(window.scrollBy).toHaveBeenCalledWith({
      top: window.innerHeight,
      behavior: 'smooth',
    });
  });

  it('does not push when clicking the active tab or pressing a modified number shortcut', async () => {
    const user = userEvent.setup();

    renderNavigation();

    await user.click(screen.getByRole('button', { name: '2. People' }));
    fireEvent.keyDown(document, { key: '5', ctrlKey: true });

    expect(mockPush).not.toHaveBeenCalled();
  });

  it('asks before navigating away when the YAML editor has unsaved changes', async () => {
    const user = userEvent.setup();
    (confirm as unknown as ReturnType<typeof vi.fn>).mockReturnValue(false);

    renderNavigation({ tabSwitchWarningActive: true });

    await user.click(screen.getByRole('button', { name: '5. Shift Requests' }));

    expect(confirm).toHaveBeenCalledWith('You have unsaved edits. Leave this page without saving?');
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('updates active tab styling on rerender when pathname changes', () => {
    const { rerender } = renderNavigation();

    expect(screen.getByRole('button', { name: '2. People' }).className).toContain('text-blue-600');

    mockUsePathname.mockReturnValue('/save-and-load');
    rerender(
      <UnsavedEditingStateProvider>
        <Navigation />
      </UnsavedEditingStateProvider>
    );

    expect(screen.getByRole('button', { name: '10. Save and Load' }).className).toContain('text-blue-600');
    expect(screen.getByRole('button', { name: '2. People' }).className).not.toContain('text-blue-600');
  });

  it('does nothing on boundary arrow navigation and supports ArrowUp scrolling', () => {
    mockUsePathname.mockReturnValue('/');
    const { rerender } = renderNavigation();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    expect(mockPush).not.toHaveBeenCalled();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    expect(window.scrollBy).toHaveBeenCalledWith({
      top: -window.innerHeight,
      behavior: 'smooth',
    });

    mockUsePathname.mockReturnValue('/optimize-and-export');
    rerender(
      <UnsavedEditingStateProvider>
        <Navigation />
      </UnsavedEditingStateProvider>
    );

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('ignores shortcuts while textarea, select, or contenteditable elements are focused', () => {
    renderNavigation();

    const textarea = document.createElement('textarea');
    document.body.appendChild(textarea);
    textarea.focus();
    fireEvent.keyDown(document, { key: '5' });
    textarea.blur();
    textarea.remove();

    const select = document.createElement('select');
    document.body.appendChild(select);
    select.focus();
    fireEvent.keyDown(document, { key: '5' });
    select.blur();
    select.remove();

    const editable = document.createElement('div');
    editable.setAttribute('contenteditable', 'true');
    document.body.appendChild(editable);
    editable.focus();
    fireEvent.keyDown(document, { key: '5' });
    editable.blur();
    editable.remove();

    expect(mockPush).not.toHaveBeenCalled();
  });

  it('navigates home with the 0 shortcut', () => {
    renderNavigation();

    fireEvent.keyDown(document, { key: '0' });

    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('updates active-tab styling on rerender even while an editable element remains focused', () => {
    const { rerender } = renderNavigation();
    const editable = document.createElement('div');
    editable.setAttribute('contenteditable', 'true');
    document.body.appendChild(editable);
    editable.focus();

    fireEvent.keyDown(document, { key: '5' });
    expect(mockPush).not.toHaveBeenCalled();

    mockUsePathname.mockReturnValue('/shift-requests');
    rerender(
      <UnsavedEditingStateProvider>
        <Navigation />
      </UnsavedEditingStateProvider>
    );

    expect(screen.getByRole('button', { name: '5. Shift Requests' }).className).toContain('text-blue-600');
    expect(screen.getByRole('button', { name: '2. People' }).className).not.toContain('text-blue-600');

    editable.blur();
    editable.remove();
  });

  it('removes keyboard listeners on unmount', () => {
    const { unmount } = renderNavigation();

    unmount();
    fireEvent.keyDown(document, { key: '5' });

    expect(mockPush).not.toHaveBeenCalled();
  });
});
