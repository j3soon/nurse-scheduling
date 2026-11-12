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

import { act, render, waitFor } from '@testing-library/react';
import { I18nProvider } from '@/i18n/I18nProvider';
import { LOCALE_STORAGE_KEY } from '@/i18n/messages';
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
    localStorage.clear();
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

  it('localizes the widget and form, and reuses each language actor', async () => {
    mockPhone(false);
    mocks.pathname = '/';
    localStorage.setItem(LOCALE_STORAGE_KEY, 'zh-TW');
    const english = { appendToDom: vi.fn(), removeFromDom: vi.fn() };
    const chinese = { appendToDom: vi.fn(), removeFromDom: vi.fn() };
    mocks.createWidget.mockImplementation(options => options?.triggerLabel === '意見回饋' ? chinese : english);
    render(<I18nProvider><FeedbackWidget /></I18nProvider>);
    await waitFor(() => expect(mocks.createWidget).toHaveBeenLastCalledWith(expect.objectContaining({
      triggerLabel: '意見回饋', formTitle: '傳送回饋', nameLabel: '姓名', emailLabel: '電子郵件',
      cancelButtonLabel: '取消', addScreenshotButtonLabel: '新增螢幕截圖',
      successMessageText: '感謝您的回報！',
    })));
    act(() => {
      localStorage.setItem(LOCALE_STORAGE_KEY, 'en');
      window.dispatchEvent(new StorageEvent('storage', { key: LOCALE_STORAGE_KEY, newValue: 'en' }));
    });
    expect(chinese.removeFromDom).toHaveBeenCalled();
    expect(english.appendToDom).toHaveBeenCalled();
    expect(mocks.createWidget).toHaveBeenCalledTimes(2);
    localStorage.clear();
  });

});
