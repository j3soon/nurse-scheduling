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
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { ModelControls } from './ModelControls';

const catalog = {
  default_model: 'fast', models: [
    { id: 'fast', name: 'Fast', context_tokens: null, reasoning_options: [{ id: 'default', label: 'Default' }] },
    { id: 'deep', name: 'Deep', context_tokens: 32000, reasoning_options: [
      { id: 'default', label: 'Default' }, { id: 'off', label: 'Off' }, { id: 'high', label: 'High' },
    ] },
  ],
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('shows supported reasoning choices and restores the choice when switching back', async () => {
  const user = userEvent.setup();
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => catalog });
  vi.stubGlobal('fetch', fetch);
  const onChange = vi.fn();
  const view = render(<ModelControls endpoint="https://ai.example" token="chat-key" disabled={false} onChange={onChange} />);
  await waitFor(() => expect(screen.getByLabelText('AI model')).toHaveValue('fast'));
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer chat-key');
  expect(screen.queryByLabelText('Reasoning')).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('AI model'), 'deep');
  await user.selectOptions(screen.getByLabelText('Reasoning'), 'high');
  await user.selectOptions(screen.getByLabelText('AI model'), 'fast');
  expect(onChange).toHaveBeenLastCalledWith({ model: 'fast', reasoning: 'default' });
  await user.selectOptions(screen.getByLabelText('AI model'), 'deep');
  expect(screen.getByLabelText('Reasoning')).toHaveValue('high');
  view.rerender(<ModelControls endpoint="https://ai.example" token="chat-key" disabled onChange={onChange} />);
  expect(screen.getByLabelText('AI model')).toBeDisabled();
  expect(screen.getByLabelText('Reasoning')).toBeDisabled();
});

it('loads models with the new credential and resets choices that it cannot use', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
  const onChange = vi.fn();
  const view = render(<ModelControls endpoint="https://ai.example" token="first" disabled={false} onChange={onChange} />);
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ model: 'fast', reasoning: 'default' }));
  view.rerender(<ModelControls endpoint="https://ai.example" token="second" disabled={false} onChange={onChange} />);
  expect(onChange).toHaveBeenLastCalledWith(undefined);
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ model: 'fast', reasoning: 'default' }));
  expect(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).toEqual({ Authorization: 'Bearer second' });
});

it('reports discovery errors and allows retry without accepting a stale selection', async () => {
  const user = userEvent.setup();
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('Gateway unavailable'))
    .mockResolvedValue({ ok: true, json: async () => catalog }));
  const onChange = vi.fn();
  render(<ModelControls endpoint="https://ai.example" token={null} disabled={false} onChange={onChange} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Gateway unavailable');
  expect(onChange).toHaveBeenLastCalledWith(undefined);
  await user.click(screen.getByText('Retry'));
  await waitFor(() => expect(screen.getByLabelText('AI model')).toHaveValue('fast'));
});
