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

import { render, screen } from '@testing-library/react';
import PageDocumentationLink from '@/components/PageDocumentationLink';

describe('PageDocumentationLink', () => {
  it('links the help icon to the matching same-origin documentation page', () => {
    render(<PageDocumentationLink href="/docs/user-guide/dates/" label="Dates" />);

    expect(screen.getByRole('link', { name: 'Dates documentation' })).toHaveAttribute(
      'href',
      '/docs/user-guide/dates/',
    );
    expect(screen.getByRole('link', { name: 'Dates documentation' })).toHaveAttribute('target', '_blank');
  });
});
