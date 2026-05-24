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

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ToggleButton from '@/components/ToggleButton';

describe('ToggleButton', () => {
  it('renders label and handles click', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();

    render(<ToggleButton label="Show advanced" isToggled={false} onToggle={onToggle} />);

    const button = screen.getByRole('button', { name: /show advanced/i });
    await user.click(button);

    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
