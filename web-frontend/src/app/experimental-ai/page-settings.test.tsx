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

import {
  mockCreateSession,
  mockGetBackendVersion,
  mockGetCapabilities,
  mockGetModels,
  mockGetSessionModelSelection,
  mockUpdateSessionModelSelection,
  mockGetSessionStatus,
  mockRunEvents,
  mockSendMessage,
  defaultCapabilities,
  seedRecentChat,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import { AI_HISTORY_STORAGE_KEY } from './chatHistory';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('protects drafts on selection and scopes credentials to the selected backend', async () => {
    seedRecentChat('external-session', 'https://example.com/ai');
    localStorage.setItem('nurse-scheduling-ai-auth', JSON.stringify({ tokens: { 'https://example.com/ai': 'external-token' } }));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const history = screen.getByRole('complementary', { name: 'Recent chats' });
    const entry = await within(history).findByRole('button', { name: /^Review external-session/ });
    const input = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    await user.type(input, 'Unsaved draft');
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await user.click(entry);
    expect(input).toHaveValue('Unsaved draft');
    expect(mockGetSessionStatus).not.toHaveBeenCalled();
    confirmation.mockReturnValue(true);
    await user.click(entry);
    expect(input).toHaveValue('');
    await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalledWith('external-session', 'external-token', 'https://example.com/ai'));
    expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).not.toContain('external-token');
  });

  it('uses optimizer identity when the deployed AI capabilities omit the app version', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, app_version: undefined });
    mockGetBackendVersion.mockResolvedValue('v0.2.0-production');
    render(<ExperimentalAiPage />);
    await waitFor(() => expect(screen.getByText(/^Backend(?:\s|$)/)).toHaveTextContent('Backend v0.2.0-production'));
    expect(mockGetBackendVersion).toHaveBeenCalledWith(expect.any(AbortSignal), '/ai');
  });

  it('warns about the AI service version even when the parent backend reports another build', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, app_version: 'v0.4.2-ai' });
    render(<ExperimentalAiPage />);

    const versions = screen.getByRole('group', { name: 'AI versions' });
    await waitFor(() => expect(versions).toHaveTextContent('Backend v0.4.2-ai'));
    expect(versions).toHaveTextContent('Frontend and backend versions do not match. If nothing breaks, you can continue.');
  });

  it('shows an unknown backend version without declaring a mismatch', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, app_version: undefined });
    mockGetBackendVersion.mockResolvedValue(undefined);
    render(<ExperimentalAiPage />);

    await waitFor(() => expect(mockGetBackendVersion).toHaveBeenCalled());
    const versions = screen.getByRole('group', { name: 'AI versions' });
    expect(versions).toHaveTextContent('Backend unknown');
    expect(versions).not.toHaveTextContent('versions do not match');
  });

  it('selects localhost and locks that server after the conversation starts', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.click(screen.getByRole('button', { name: 'Change' }));
    await user.click(screen.getByRole('button', { name: 'Use localhost' }));

    expect(screen.getByText('http://localhost:8001')).toBeInTheDocument();
    expect(screen.getByText(/unofficially hosted.*privacy and data retention practices may vary/i)).toBeInTheDocument();
    expect(window.localStorage.getItem('nurse-scheduling-ai-server')).toBe('http://localhost:8001');
    await waitFor(() => expect(mockGetCapabilities).toHaveBeenLastCalledWith(
      expect.any(AbortSignal),
      'http://localhost:8001',
    ));

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(mockCreateSession).toHaveBeenCalledWith(
      'description: current Schedule Spec\n',
      null,
      'http://localhost:8001',
      undefined,
    );
    expect(screen.getByRole('button', { name: 'Change' })).toBeDisabled();
    expect(screen.getByText('This server is locked for the current conversation. Start a new chat to change servers.')).toBeInTheDocument();
  });

  it('normalizes a custom AI server URL', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.click(screen.getByRole('button', { name: 'Change' }));
    const serverInput = screen.getByRole('textbox', { name: 'Custom AI server URL' });
    expect(serverInput).toHaveValue('/ai');
    await user.clear(serverInput);
    await user.type(serverInput, 'ai.example.com/');
    await user.click(screen.getByRole('button', { name: 'Use custom' }));

    expect(screen.getByText('https://ai.example.com')).toBeInTheDocument();
    expect(window.localStorage.getItem('nurse-scheduling-ai-server')).toBe('https://ai.example.com');
  });

  it('locks the model and saves reasoning changes for the next queued turn', async () => {
    const original = { model: 'deep', reasoning: 'high' };
    const current = { model: 'deep', reasoning: 'off' };
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, model_selection: true });
    mockGetModels.mockResolvedValue({ default_model: 'fast', models: [
      { id: 'fast', name: 'Fast', default_reasoning: 'default', reasoning_options: [{ id: 'default', label: 'Default' }] },
      { id: 'deep', name: 'Deep', default_reasoning: 'high', reasoning_options: [
        { id: 'off', label: 'Off' }, { id: 'high', label: 'High' },
      ] },
    ] });
    mockGetSessionModelSelection.mockResolvedValue({ selection: original, locked: false });
    let finishStream!: () => void;
    let finishSave!: (saved: { selection: typeof current; locked: boolean }) => void;
    mockUpdateSessionModelSelection.mockImplementation(() => new Promise(resolve => { finishSave = resolve; }));
    mockRunEvents.mockImplementationOnce(async (_session: string, _question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'model_selection', selection: original });
      callbacks.onEvent({ type: 'delta', text: 'The first model is streaming.' });
      await new Promise<void>(resolve => { finishStream = resolve; });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await waitFor(() => expect(screen.getByLabelText('AI model')).toHaveValue('fast'));
    await user.selectOptions(screen.getByLabelText('AI model'), 'deep');
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    await user.type(composer, 'First question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('The first model is streaming.');
    await waitFor(() => expect(composer).toBeEnabled());
    expect(screen.getByLabelText('AI model')).toBeDisabled();
    expect(screen.getByLabelText('Reasoning')).toBeEnabled();
    await user.type(composer, 'Next question');
    await user.keyboard('{Enter}');
    await user.selectOptions(screen.getByLabelText('Reasoning'), 'off');
    expect(mockUpdateSessionModelSelection).toHaveBeenCalledWith('session-id', current, null, '/ai');
    await act(async () => finishStream());
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    await act(async () => finishSave({ selection: current, locked: true }));
    await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(2));
    expect(mockCreateSession).toHaveBeenCalledWith('description: current Schedule Spec\n', null, '/ai', original);
    expect(mockSendMessage.mock.calls[0][5].selection).toEqual(original);
    expect(mockSendMessage.mock.calls[1][5].selection).toEqual(current);
    expect(screen.getByText('deep · high')).toBeInTheDocument();
  });

  it('requires the advertised AI token and uses a session-only credential', async () => {
    mockGetCapabilities.mockResolvedValueOnce({
      ...defaultCapabilities,
      auth: { required: true, scheme: 'bearer' },
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    const tokenButton = await screen.findByRole('button', { name: 'Enter token for AI assistant' });
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    expect(composer).toBeEnabled();
    await user.type(composer, 'Who works?');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }));
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(composer).toHaveValue('Who works?');
    await user.click(tokenButton);
    await user.type(screen.getByLabelText('Token for AI assistant'), 'ai-session-token');
    await user.click(screen.getByRole('button', { name: 'Save token for AI assistant' }));

    expect(screen.getByText('Token set for this session')).toBeInTheDocument();
    expect(window.localStorage.getItem('nurse-scheduling-ai-auth')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(mockCreateSession).toHaveBeenCalledWith(
      'description: current Schedule Spec\n',
      'ai-session-token',
      '/ai',
      undefined,
    ));
    expect(mockRunEvents.mock.calls[0][4]).toBe('ai-session-token');
  });

  it('remembers the AI token only when requested', async () => {
    mockGetCapabilities.mockResolvedValueOnce({
      ...defaultCapabilities,
      auth: { required: true, scheme: 'bearer' },
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.click(await screen.findByRole('button', { name: 'Enter token for AI assistant' }));
    await user.type(screen.getByLabelText('Token for AI assistant'), 'remembered-ai-token');
    await user.click(screen.getByRole('checkbox', { name: /remember on this device/i }));
    await user.click(screen.getByRole('button', { name: 'Save token for AI assistant' }));

    expect(screen.getByText('Token saved on this device')).toBeInTheDocument();
    expect(screen.getByText('Token saved on this device').compareDocumentPosition(
      screen.getByRole('group', { name: 'AI versions' }),
    ) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(JSON.parse(window.localStorage.getItem('nurse-scheduling-ai-auth') ?? '{}')).toEqual({
      tokens: { '/ai': 'remembered-ai-token' },
    });
  });

  it('prompts for a replacement when the AI service rejects a token', async () => {
    mockGetCapabilities.mockResolvedValueOnce({
      ...defaultCapabilities,
      auth: { required: true, scheme: 'bearer' },
    });
    mockCreateSession.mockRejectedValueOnce(Object.assign(new Error('Invalid credentials'), { status: 401 }));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.click(await screen.findByRole('button', { name: 'Enter token for AI assistant' }));
    await user.type(screen.getByLabelText('Token for AI assistant'), 'stale-ai-token');
    await user.click(screen.getByRole('button', { name: 'Save token for AI assistant' }));
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'AI credentials were rejected. Enter the current AI token and try again.',
    );
    expect(screen.getByLabelText('Token for AI assistant')).toHaveValue('');
  });

  it('shows an error when capability discovery fails', async () => {
    mockGetCapabilities.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    render(<ExperimentalAiPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load AI capabilities from /ai. Check that the AI backend is reachable from this browser.',
    );
    expect(screen.queryByLabelText('Attach files')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
  });

  it('animates the thinking indicator while awaiting the first response token', async () => {
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(() => new Promise<void>(resolve => {
      finishStream = resolve;
    }));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Think about this.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const thinking = await screen.findByRole('status', { name: 'Thinking' });
    expect(thinking.querySelectorAll('[style*="animation-delay"]')).toHaveLength(3);

    finishStream?.();
    await waitFor(() => expect(screen.queryByRole('status', { name: 'Thinking' })).not.toBeInTheDocument());
  });
});
