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
import AppVersionText from '@/components/AppVersionText';

describe('AppVersionText', () => {
  it('renders plain tag when no versionHref is provided', () => {
    const { container } = render(
      <div>
        <AppVersionText version="v1.2.3" />
      </div>,
    );

    expect(screen.getByText('v1.2.3')).toBeInTheDocument();
    expect(container.querySelector('a')).toBeNull();
  });

  it('renders linked tag when versionHref is provided', () => {
    render(
      <div>
        <AppVersionText version="v1.2.3" versionHref="https://example.com/tag/v1.2.3" />
      </div>,
    );

    const tagLink = screen.getByRole('link', { name: 'v1.2.3' });
    expect(tagLink).toHaveAttribute('href', 'https://example.com/tag/v1.2.3');
  });

  it('renders git-describe style tagged commit with hash link and dirty suffix', () => {
    const { container } = render(
      <div>
        <AppVersionText version="v1.2.3-4-gabc1234-dirty" />
      </div>,
    );

    expect(container).toHaveTextContent('v1.2.3-4-gabc1234-dirty');

    const hashLink = screen.getByRole('link', { name: 'abc1234' });
    expect(hashLink).toHaveAttribute('href', 'https://github.com/j3soon/nurse-scheduling/tree/abc1234');
  });

  it('renders hash-only format without -g prefix', () => {
    render(
      <div>
        <AppVersionText version="deadbeef" />
      </div>,
    );

    const hashLink = screen.getByRole('link', { name: 'deadbeef' });
    expect(hashLink).toHaveAttribute('href', 'https://github.com/j3soon/nurse-scheduling/tree/deadbeef');
    expect(screen.queryByText('-g')).not.toBeInTheDocument();
  });

  it('renders unsupported fallback versions as plain text', () => {
    render(
      <div>
        <AppVersionText version="v0.0.0-unknown" />
      </div>,
    );

    expect(screen.getByText('v0.0.0-unknown')).toBeInTheDocument();
  });
});
