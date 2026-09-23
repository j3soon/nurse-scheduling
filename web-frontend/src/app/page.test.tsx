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

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Home from './page';

const createNewState = vi.fn();
const loadFromYaml = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: () => ({ createNewState, loadFromYaml }),
}));

vi.mock('@/utils/version', () => ({
  areBuildOriginsEquivalent: (first: string, second: string) => first === second,
  CURRENT_APP_VERSION: 'v1.0.0',
  fetchReleaseBranches: vi.fn().mockResolvedValue([]),
  isStableReleaseVersion: () => true,
}));

describe('Home', () => {
  beforeEach(() => {
    createNewState.mockReset();
    loadFromYaml.mockReset();
    push.mockReset();
    vi.unstubAllGlobals();
  });

  it('bundles the canonical 87-person testcase without modification', () => {
    const bundled = readFileSync(resolve('public/examples/large-ward-with-87-people-2025-11.yaml'));
    const canonical = readFileSync(resolve('../core/tests/testcases/real/large-ward-with-87-people-2025-11.yaml'));

    expect(bundled).toEqual(canonical);
  });

  it('keeps the primary new schedule action empty', async () => {
    const user = userEvent.setup();
    render(<Home />);

    await user.click(screen.getByRole('button', { name: 'New Schedule' }));
    expect(screen.getByText(/Start an empty schedule/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Create empty schedule' }));

    expect(createNewState).toHaveBeenCalledOnce();
    expect(loadFromYaml).not.toHaveBeenCalled();
  });

  it('loads the realistic example through the normal YAML import path', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(`
apiVersion: alpha
description: Real example
people:
  items:
    - id: P1
`),
    }));
    render(<Home />);

    await user.click(screen.getByRole('button', { name: 'Choose new schedule type' }));
    await user.click(screen.getByRole('button', { name: /87-person example/ }));
    expect(screen.getByText(/Load the 87-person example/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load example' }));

    await waitFor(() => expect(loadFromYaml).toHaveBeenCalledWith(expect.objectContaining({
      apiVersion: 'alpha',
      description: 'Real example',
    })));
    expect(fetch).toHaveBeenCalledWith('/examples/large-ward-with-87-people-2025-11.yaml');
    expect(createNewState).not.toHaveBeenCalled();
  });
});
