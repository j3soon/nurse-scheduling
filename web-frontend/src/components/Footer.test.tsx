/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */

import { render, screen } from '@testing-library/react';
import Footer from '@/components/Footer';

const mockUsePathname = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
}));

describe('Footer', () => {
  it('renders the project information on regular pages', () => {
    mockUsePathname.mockReturnValue('/people');
    render(<Footer />);

    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nurse Scheduling Project' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AGPL-3.0' })).toBeInTheDocument();
  });

  it('does not render on the AI chat page', () => {
    mockUsePathname.mockReturnValue('/experimental-ai');
    render(<Footer />);

    expect(screen.queryByRole('contentinfo')).not.toBeInTheDocument();
  });
});
