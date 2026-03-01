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
});
