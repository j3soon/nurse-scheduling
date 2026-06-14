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

import { fireEvent, render, screen } from '@testing-library/react';
import { CalendarDayButton, getCalendarDayCategoryClassName } from '@/components/CalendarMonthView';

describe('CalendarMonthView primitives', () => {
  it('responds only to left-mouse selection handlers', () => {
    const onMouseDown = vi.fn();
    const onMouseUp = vi.fn();

    render(
      <CalendarDayButton
        date={new Date('2026-05-01')}
        ariaLabel="May 1"
        stateClassName=""
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
      />,
    );

    const button = screen.getByRole('button', { name: 'May 1' });
    fireEvent.mouseDown(button, { button: 2 });
    fireEvent.mouseUp(button, { button: 2 });
    fireEvent.mouseDown(button, { button: 0 });
    fireEvent.mouseUp(button, { button: 0 });

    expect(onMouseDown).toHaveBeenCalledTimes(1);
    expect(onMouseUp).toHaveBeenCalledTimes(1);
  });

  it('prevents Enter and Space activation', () => {
    render(
      <CalendarDayButton
        date={new Date('2026-05-01')}
        ariaLabel="May 1"
        stateClassName=""
      />,
    );

    const button = screen.getByRole('button', { name: 'May 1' });
    expect(fireEvent.keyDown(button, { key: 'Enter' })).toBe(false);
    expect(fireEvent.keyDown(button, { key: ' ' })).toBe(false);
  });

  it('uses quiet normal-day styling and text emphasis for Taiwan calendar exceptions', () => {
    expect(getCalendarDayCategoryClassName(new Date('2025-02-08')))
      .toContain('font-medium text-slate-700');
    expect(getCalendarDayCategoryClassName(new Date('2025-02-09')))
      .toContain('bg-amber-50/70');
    expect(getCalendarDayCategoryClassName(new Date('2025-02-28')))
      .toContain('font-medium text-amber-800');
    expect(getCalendarDayCategoryClassName(new Date('2025-02-10')))
      .toContain('text-slate-700');
    expect(getCalendarDayCategoryClassName(new Date('2027-02-07')))
      .toContain('bg-amber-50/70');
    expect(getCalendarDayCategoryClassName(new Date('2027-02-08')))
      .toContain('bg-white');
  });
});
