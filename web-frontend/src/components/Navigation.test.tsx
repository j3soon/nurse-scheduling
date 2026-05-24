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
import Navigation from '@/components/Navigation';

const mockPush = vi.hoisted(() => vi.fn());
const mockUsePathname = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockUsePathname(),
}));

describe('Navigation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockPush.mockReset();
    mockUsePathname.mockReturnValue('/people');
    vi.spyOn(window, 'scrollBy').mockImplementation(() => undefined);
  });

  it('navigates when a tab button is clicked', async () => {
    const user = userEvent.setup();

    render(<Navigation />);

    await user.click(screen.getByRole('button', { name: '5. Shift Requests' }));

    expect(mockPush).toHaveBeenCalledWith('/shift-requests');
  });

  it('supports number-key shortcut navigation when no input is focused', () => {
    render(<Navigation />);

    fireEvent.keyDown(document, { key: '5' });

    expect(mockPush).toHaveBeenCalledWith('/shift-requests');
  });

  it('does not use number shortcuts while an input is focused', () => {
    render(<Navigation />);

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(document, { key: '5' });

    expect(mockPush).not.toHaveBeenCalled();
    input.blur();
    input.remove();
  });

  it('navigates with arrow keys and scroll shortcuts', () => {
    render(<Navigation />);

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

    render(<Navigation />);

    await user.click(screen.getByRole('button', { name: '2. People' }));
    fireEvent.keyDown(document, { key: '5', ctrlKey: true });

    expect(mockPush).not.toHaveBeenCalled();
  });

  it('updates active tab styling on rerender when pathname changes', () => {
    const { rerender } = render(<Navigation />);

    expect(screen.getByRole('button', { name: '2. People' }).className).toContain('text-blue-600');

    mockUsePathname.mockReturnValue('/save-and-load');
    rerender(<Navigation />);

    expect(screen.getByRole('button', { name: '10. Save and Load' }).className).toContain('text-blue-600');
    expect(screen.getByRole('button', { name: '2. People' }).className).not.toContain('text-blue-600');
  });

  it('does nothing on boundary arrow navigation and supports ArrowUp scrolling', () => {
    mockUsePathname.mockReturnValue('/');
    const { rerender } = render(<Navigation />);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    expect(mockPush).not.toHaveBeenCalled();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    expect(window.scrollBy).toHaveBeenCalledWith({
      top: -window.innerHeight,
      behavior: 'smooth',
    });

    mockUsePathname.mockReturnValue('/optimize-and-export');
    rerender(<Navigation />);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('ignores shortcuts while textarea, select, or contenteditable elements are focused', () => {
    render(<Navigation />);

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
    render(<Navigation />);

    fireEvent.keyDown(document, { key: '0' });

    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('updates active-tab styling on rerender even while an editable element remains focused', () => {
    const { rerender } = render(<Navigation />);
    const editable = document.createElement('div');
    editable.setAttribute('contenteditable', 'true');
    document.body.appendChild(editable);
    editable.focus();

    fireEvent.keyDown(document, { key: '5' });
    expect(mockPush).not.toHaveBeenCalled();

    mockUsePathname.mockReturnValue('/shift-requests');
    rerender(<Navigation />);

    expect(screen.getByRole('button', { name: '5. Shift Requests' }).className).toContain('text-blue-600');
    expect(screen.getByRole('button', { name: '2. People' }).className).not.toContain('text-blue-600');

    editable.blur();
    editable.remove();
  });

  it('removes keyboard listeners on unmount', () => {
    const { unmount } = render(<Navigation />);

    unmount();
    fireEvent.keyDown(document, { key: '5' });

    expect(mockPush).not.toHaveBeenCalled();
  });
});
