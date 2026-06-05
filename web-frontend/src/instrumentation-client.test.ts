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

import { beforeEach, describe, expect, it, vi } from 'vitest';

const sentryMocks = vi.hoisted(() => ({
  captureRouterTransitionStart: vi.fn(),
  feedbackIntegration: vi.fn((options: unknown) => ({ name: 'feedback', options })),
  init: vi.fn(),
  replayIntegration: vi.fn(() => ({ name: 'replay' })),
  setTag: vi.fn(),
}));

vi.mock('@sentry/nextjs', () => sentryMocks);

describe('instrumentation-client', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    delete process.env.NEXT_PUBLIC_DISABLE_SENTRY;
  });

  it('forces the Sentry feedback widget to use the light color scheme', async () => {
    await import('./instrumentation-client');

    expect(sentryMocks.feedbackIntegration).toHaveBeenCalledWith(
      expect.objectContaining({
        colorScheme: 'light',
        enableScreenshot: true,
        isEmailRequired: true,
        isNameRequired: true,
      }),
    );
  });
});
