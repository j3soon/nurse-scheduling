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

import { render } from '@testing-library/react';
import FeedbackWidget from '@/components/FeedbackWidget';

const mocks = vi.hoisted(() => ({
  pathname: '/',
  actor: { appendToDom: vi.fn(), removeFromDom: vi.fn() },
  createWidget: vi.fn(),
}));

vi.mock('next/navigation', () => ({ usePathname: () => mocks.pathname }));
vi.mock('@sentry/nextjs', () => ({ getFeedback: () => ({ createWidget: mocks.createWidget }) }));

function mockPhone(matches: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() });
}

describe('FeedbackWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createWidget.mockReturnValue(mocks.actor);
  });

  it('shows the floating button on phones except on the AI chat page', () => {
    mockPhone(true);
    mocks.pathname = '/people';
    const { rerender } = render(<FeedbackWidget />);
    expect(mocks.createWidget).toHaveBeenCalledTimes(1);
    mocks.pathname = '/experimental-ai';
    rerender(<FeedbackWidget />);
    expect(mocks.actor.removeFromDom).toHaveBeenCalledTimes(1);
    mocks.pathname = '/people';
    rerender(<FeedbackWidget />);
    expect(mocks.actor.appendToDom).toHaveBeenCalledTimes(1);
    expect(mocks.createWidget).toHaveBeenCalledTimes(1);
  });

  it('keeps the floating button on the AI chat page on desktop', () => {
    mockPhone(false);
    mocks.pathname = '/experimental-ai';
    render(<FeedbackWidget />);
    expect(mocks.createWidget).toHaveBeenCalledTimes(1);
  });
});
