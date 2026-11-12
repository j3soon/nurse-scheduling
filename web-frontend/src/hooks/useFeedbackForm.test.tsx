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

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { I18nProvider, useI18n } from '@/i18n/I18nProvider';
import { useFeedbackForm } from './useFeedbackForm';

const mocks = vi.hoisted(() => ({ createForm: vi.fn(), captureException: vi.fn() }));
vi.mock('@sentry/nextjs', () => ({
  getFeedback: () => ({ createForm: mocks.createForm }),
  captureException: mocks.captureException,
}));

function Harness({ tick = 0 }: { tick?: number }) {
  const ref = useFeedbackForm();
  const { setLocale } = useI18n();
  return <><button ref={ref}>Feedback {tick}</button><button onClick={() => setLocale('zh-TW')}>Chinese</button></>;
}

let draft: HTMLTextAreaElement;
let form: { appendToDom: ReturnType<typeof vi.fn>; removeFromDom: ReturnType<typeof vi.fn>; open: ReturnType<typeof vi.fn> };
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  draft = document.createElement('textarea');
  draft.setAttribute('aria-label', 'Feedback draft');
  form = { appendToDom: vi.fn(() => document.body.append(draft)), removeFromDom: vi.fn(() => draft.remove()), open: vi.fn() };
  mocks.createForm.mockReset().mockResolvedValue(form);
});
afterEach(() => { draft.remove(); localStorage.clear(); });

it('keeps an open draft across streaming renders and language changes, then opens the next form in Chinese', async () => {
  const view = render(<I18nProvider><Harness /></I18nProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Feedback 0' }));
  await screen.findByRole('textbox', { name: 'Feedback draft' });
  expect(mocks.createForm).toHaveBeenLastCalledWith(expect.objectContaining({ nameLabel: 'Name', formTitle: 'Send Feedback' }));
  fireEvent.change(draft, { target: { value: 'Keep this report' } });
  view.rerender(<I18nProvider><Harness tick={1} /></I18nProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Chinese' }));
  expect(draft).toBeInTheDocument();
  expect(draft).toHaveValue('Keep this report');
  expect(form.removeFromDom).not.toHaveBeenCalled();
  act(() => mocks.createForm.mock.calls[0][0].onFormClose());
  expect(draft).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Feedback 1' }));
  await waitFor(() => expect(mocks.createForm).toHaveBeenCalledTimes(2));
  expect(mocks.createForm).toHaveBeenLastCalledWith(expect.objectContaining({ nameLabel: '姓名', formTitle: '傳送回饋', errorEmptyMessageText: '請填寫回饋內容後再傳送。' }));
});

it('does not open a form after unmount or load duplicate dialogs for repeated clicks', async () => {
  let finish!: (value: typeof form) => void;
  mocks.createForm.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const view = render(<I18nProvider><Harness /></I18nProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Feedback 0' }));
  fireEvent.click(screen.getByRole('button', { name: 'Feedback 0' }));
  expect(mocks.createForm).toHaveBeenCalledTimes(1);
  view.unmount();
  await act(async () => { finish(form); });
  expect(form.open).not.toHaveBeenCalled();
  expect(form.removeFromDom).toHaveBeenCalledTimes(1);
});

it('reports a dialog loading failure and lets a later click retry', async () => {
  const error = new Error('Dialog could not load');
  mocks.createForm.mockRejectedValueOnce(error);
  render(<I18nProvider><Harness /></I18nProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Feedback 0' }));
  await waitFor(() => expect(mocks.captureException).toHaveBeenCalledWith(error));
  fireEvent.click(screen.getByRole('button', { name: 'Feedback 0' }));
  await waitFor(() => expect(form.open).toHaveBeenCalledTimes(1));
});
