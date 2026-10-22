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

import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { ModelControls } from './ModelControls';

const catalog = {
  default_model: 'fast', models: [
    { id: 'fast', name: 'Fast', context_tokens: null, default_reasoning: 'default', reasoning_options: [{ id: 'default', label: 'Default' }] },
    { id: 'deep', name: 'Deep', context_tokens: 32000, default_reasoning: 'off', reasoning_options: [
      { id: 'off', label: 'Off' }, { id: 'high', label: 'High' },
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
  expect(screen.getByLabelText('Reasoning')).toHaveValue('off');
  expect(screen.queryByRole('option', { name: 'Default', exact: true })).not.toBeInTheDocument();
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
  expect(screen.getByLabelText('AI model')).toBeDisabled();
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

it('restores the session choice and saves rapid edits in order while controls stay enabled', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  let finishFirst!: (response: object) => void;
  const writes: object[] = [];
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, request?: RequestInit) => {
    if (url.endsWith('/models')) return { ok: true, json: async () => catalog };
    if (request?.method !== 'PUT') return { ok: true, json: async () => ({ model: 'deep', reasoning: 'high' }) };
    const selection = JSON.parse(request.body as string);
    writes.push(selection);
    if (writes.length === 1) return new Promise(resolve => { finishFirst = resolve; });
    return { ok: true, json: async () => selection };
  }));
  render(<ModelControls endpoint="https://ai.example" token="chat-key" sessionId="session" disabled={false} onChange={onChange} />);
  await waitFor(() => expect(screen.getByLabelText('Reasoning')).toHaveValue('high'));
  expect(onChange).toHaveBeenLastCalledWith({ model: 'deep', reasoning: 'high' });
  await user.selectOptions(screen.getByLabelText('Reasoning'), 'off');
  await user.selectOptions(screen.getByLabelText('AI model'), 'fast');
  expect(writes).toEqual([{ model: 'deep', reasoning: 'off' }]);
  expect(screen.getByLabelText('AI model')).toBeEnabled();
  expect(onChange).toHaveBeenLastCalledWith(undefined);
  finishFirst({ ok: true, json: async () => ({ model: 'deep', reasoning: 'off' }) });
  await waitFor(() => expect(writes).toEqual([
    { model: 'deep', reasoning: 'off' }, { model: 'fast', reasoning: 'default' },
  ]));
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ model: 'fast', reasoning: 'default' }));
});

it('blocks new submissions after a save failure until the session choice reloads', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, request?: RequestInit) => {
    if (url.endsWith('/models')) return { ok: true, json: async () => catalog };
    if (request?.method === 'PUT') throw new Error('Choice could not be saved');
    return { ok: true, json: async () => ({ model: 'deep', reasoning: 'high' }) };
  }));
  render(<ModelControls endpoint="https://ai.example" token="chat-key" sessionId="session" disabled={false} onChange={onChange} />);
  await waitFor(() => expect(screen.getByLabelText('Reasoning')).toHaveValue('high'));
  await user.selectOptions(screen.getByLabelText('Reasoning'), 'off');
  expect(await screen.findByRole('alert')).toHaveTextContent('Choice could not be saved');
  expect(onChange).toHaveBeenLastCalledWith(undefined);
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ model: 'deep', reasoning: 'high' }));
});

it('saves edits made before session creation finishes instead of restoring its older choice', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  let finishSave!: (response: object) => void;
  const writes: object[] = [];
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, request?: RequestInit) => {
    if (url.endsWith('/models')) return { ok: true, json: async () => catalog };
    if (request?.method !== 'PUT') return { ok: true, json: async () => ({ model: 'deep', reasoning: 'off' }) };
    writes.push(JSON.parse(request.body as string));
    return new Promise(resolve => { finishSave = resolve; });
  }));
  const view = render(<ModelControls endpoint="https://ai.example" token="chat-key" disabled={false} onChange={onChange} />);
  await waitFor(() => expect(screen.getByLabelText('AI model')).toHaveValue('fast'));
  await user.selectOptions(screen.getByLabelText('AI model'), 'deep');
  // Creation started with Deep. The user chooses Fast before it returns a session ID.
  await user.selectOptions(screen.getByLabelText('AI model'), 'fast');
  view.rerender(<ModelControls endpoint="https://ai.example" token="chat-key" sessionId="session" disabled={false} onChange={onChange} />);
  await waitFor(() => expect(writes).toEqual([{ model: 'fast', reasoning: 'default' }]));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
  await act(async () => finishSave({ ok: true, json: async () => ({ model: 'fast', reasoning: 'default' }) }));
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ model: 'fast', reasoning: 'default' }));
  expect(screen.getByLabelText('AI model')).toHaveValue('fast');
});
