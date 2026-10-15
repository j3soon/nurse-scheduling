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
import { MobileDetails } from '@/components/MobileDetails';

describe('MobileDetails', () => {
  it('expands once when attention is needed and still lets the user collapse it', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<MobileDetails label="Details">Body</MobileDetails>);
    const toggle = screen.getByRole('button', { name: 'Details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    rerender(<MobileDetails label="Details" openWhen>Body</MobileDetails>);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(toggle);
    rerender(<MobileDetails label="Details" openWhen>Body</MobileDetails>);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});
