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

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import VersionWarningBanner from '@/components/VersionWarningBanner';

const mockFetchLatestTag = vi.hoisted(() => vi.fn());
const mockCurrentVersion = vi.hoisted(() => ({ value: 'v1.0.0' }));

vi.mock('@/utils/version', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/version')>();

  return {
    ...actual,
    get CURRENT_APP_VERSION() {
      return mockCurrentVersion.value;
    },
    fetchLatestTag: mockFetchLatestTag,
    getMajorMinor: (version: string) => {
      const match = version.match(/^(v\d+\.\d+)/);
      return match ? match[1] : null;
    },
  };
});

describe('VersionWarningBanner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockFetchLatestTag.mockReset();
    mockCurrentVersion.value = 'v1.0.0';
  });

  it('renders older-version warning and can be dismissed', async () => {
    mockFetchLatestTag.mockResolvedValue('v2.0.0');

    render(<VersionWarningBanner />);

    await waitFor(() => {
      expect(screen.getByText(/you are using an older version/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle('Dismiss version warning'));
    expect(screen.queryByText(/you are using an older version/i)).not.toBeInTheDocument();
  });

  it('renders dev-version warning for same major.minor', async () => {
    mockCurrentVersion.value = 'v1.0.3-5-gabcdef';
    mockFetchLatestTag.mockResolvedValue('v1.0.8');

    render(<VersionWarningBanner />);

    await waitFor(() => {
      expect(screen.getByText(/you are using a development version/i)).toBeInTheDocument();
    });
  });

  it('renders error warning when latest tag fetch fails', async () => {
    mockFetchLatestTag.mockResolvedValue(null);

    render(<VersionWarningBanner />);

    await waitFor(() => {
      expect(screen.getByText(/unable to check for updates/i)).toBeInTheDocument();
    });

    const link = screen.getByRole('link', { name: /check releases/i });
    expect(link).toHaveAttribute('href', 'https://nursescheduling.org');
  });
});
