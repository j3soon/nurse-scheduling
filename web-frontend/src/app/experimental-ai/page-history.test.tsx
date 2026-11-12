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
  mockGetCapabilities,
  mockGetModels,
  mockGetSessionModelSelection,
  mockUpdateSessionModelSelection,
  mockGetSessionStatus,
  mockRunEvents,
  mockSendMessage,
  mockStreamSessionEvents,
  mockStopSession,
  mockUpdateSessionSchedule,
  MockAiHttpError,
  defaultCapabilities,
  seedRecentChat,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import { AI_HISTORY_STORAGE_KEY, readChatHistory, saveChatHistory } from './chatHistory';
import type { SessionEventHandler, SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it.each(['model', 'reasoning'])('restores a recent chat without saving an unsent %s choice', async choice => {
    seedRecentChat();
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, model_selection: true });
    mockGetModels.mockResolvedValue({ default_model: 'fast', models: [
      { id: 'fast', name: 'Fast', default_reasoning: 'default', reasoning_options: [
        { id: 'default', label: 'Default' }, { id: 'high', label: 'High' },
      ] },
      { id: 'deep', name: 'Deep', default_reasoning: 'high', reasoning_options: [{ id: 'high', label: 'High' }] },
    ] });
    mockGetSessionModelSelection.mockResolvedValue({ selection: { model: 'fast', reasoning: 'default' }, locked: true });
    mockUpdateSessionModelSelection.mockRejectedValue(new MockAiHttpError('Model is fixed', 409));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await waitFor(() => expect(screen.getByLabelText('AI model')).toBeEnabled());
    await user.selectOptions(screen.getByLabelText(choice === 'model' ? 'AI model' : 'Reasoning'), choice === 'model' ? 'deep' : 'high');
    const history = screen.getByRole('complementary', { name: 'Recent chats' });
    await user.click(within(history).getByRole('button', { name: /^Review older-session/ }));
    await waitFor(() => {
      expect(screen.getByLabelText('AI model')).toHaveValue('fast');
      expect(screen.getByLabelText('AI model')).toBeDisabled();
      expect(screen.getByLabelText('Reasoning')).toHaveValue('default');
    });
    expect(mockUpdateSessionModelSelection).not.toHaveBeenCalled();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Continue this chat.');
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('does not resubmit an interrupted request just by selecting its history entry', async () => {
    const chat = seedRecentChat();
    const request = { id: 'interrupted-request', question: 'Review older-session', questionId: 'old-question', assistantId: 'old-answer', active: true };
    chat.messages = [
      { ...chat.messages[0], request },
      { ...chat.messages[1], content: '', activity: [], status: 'pending', requestId: request.id, request },
    ];
    saveChatHistory(chat);
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const history = screen.getByRole('complementary', { name: 'Recent chats' });
    await user.click(await within(history).findByRole('button', { name: /^Review older-session/ }));
    expect(await screen.findByText('This response failed before completion. Send a new message to continue.')).toBeInTheDocument();
    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
  });

  it('preserves chats across New chat and forgets an open chat without saving it again', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const input = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    await user.type(input, 'First conversation');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    const history = screen.getByRole('complementary', { name: 'Recent chats' });
    await within(history).findByRole('button', { name: /^First conversation/ });
    await user.click(within(history).getByRole('button', { name: 'New chat' }));
    expect(within(history).getByRole('button', { name: /^First conversation/ })).toBeInTheDocument();
    expect(screen.queryByText('Alice works Monday.')).not.toBeInTheDocument();
    await user.click(within(history).getByRole('button', { name: /^First conversation/ }));
    expect(await screen.findByText('Alice works Monday.')).toBeInTheDocument();
    await user.click(within(history).getByRole('button', { name: 'Remove chat: First conversation' }));
    expect(within(history).queryByRole('button', { name: /^First conversation/ })).not.toBeInTheDocument();
    expect(screen.getByText('Alice works Monday.')).toBeInTheDocument();
    await user.type(input, 'Continue forgotten conversation');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    act(() => window.dispatchEvent(new Event('pagehide')));
    expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).toBeNull();
    expect(sessionStorage.getItem('nurse-scheduling-ai-conversation')).toBeNull();
    expect(mockStopSession).not.toHaveBeenCalled();
  });

  it('clears only chat records and keeps the visible transcript and other preferences', async () => {
    seedRecentChat();
    seedRecentChat('another-session');
    localStorage.setItem('unrelated-preference', 'keep');
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const history = screen.getByRole('complementary', { name: 'Recent chats' });
    await user.click(await within(history).findByRole('button', { name: /^Review older-session/ }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await user.click(within(history).getByRole('button', { name: 'Clear history' }));
    expect(within(history).getByText('No recent chats.')).toBeInTheDocument();
    expect(screen.getByText('An earlier answer.')).toBeInTheDocument();
    expect(localStorage.getItem('unrelated-preference')).toBe('keep');
    act(() => window.dispatchEvent(new Event('pagehide')));
    expect(readChatHistory()).toEqual([]);
    expect(mockStopSession).not.toHaveBeenCalled();
  });

  it('restores the transcript and live session after navigating away', async () => {
    const user = userEvent.setup();
    const firstRender = render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works Monday?');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Alice works Monday.')).toBeInTheDocument();
    await waitFor(() => expect(window.sessionStorage.getItem('nurse-scheduling-ai-conversation')).not.toBeNull());

    firstRender.unmount();
    render(<ExperimentalAiPage />);

    expect(await screen.findByText('Who works Monday?', { selector: '.plain-content' })).toBeInTheDocument();
    expect(screen.getByText('Alice works Monday.')).toBeInTheDocument();
    expect(mockGetSessionStatus).toHaveBeenCalledWith('session-id', null, '/ai');
    expect(mockCreateSession).toHaveBeenCalledOnce();
  });

  it('flushes a pending transcript write when the page unmounts', async () => {
    vi.useFakeTimers();
    try {
      const view = render(<ExperimentalAiPage />);
      const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
      fireEvent.change(composer, { target: { value: 'Who works Monday?' } });
      await act(async () => {
        fireEvent.submit(composer.closest('form')!);
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(screen.getByText('Alice works Monday.')).toBeInTheDocument();
      view.unmount();

      const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
      expect(stored.messages).toEqual(expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: 'Who works Monday?' }),
        expect.objectContaining({ role: 'assistant', content: 'Alice works Monday.' }),
      ]));
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows and renews the exact chat expiration time', async () => {
    const now = Date.parse('2026-09-19T08:30:00Z');
    const dateNow = vi.spyOn(Date, 'now').mockReturnValue(now);
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'First question');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const firstExpiration = new Date(now + 172800 * 1000).toISOString();
    await waitFor(() => expect(screen.getByLabelText('Chat expiration')).toHaveAttribute('dateTime', firstExpiration));
    const expirationNotice = screen.getByLabelText('Chat expiration').closest('p');
    expect(expirationNotice).toHaveTextContent(/^Chat expires at /);
    expect(expirationNotice).toHaveTextContent(/Each new message extends the chat for another 2 days/);
    expect(screen.getByRole('region', { name: 'Chat messages' }).lastElementChild).toBe(expirationNotice);

    const oneHourLater = now + 60 * 60 * 1000;
    dateNow.mockReturnValue(oneHourLater);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Second question');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const renewedExpiration = new Date(oneHourLater + 172800 * 1000).toISOString();
    await waitFor(() => expect(screen.getByLabelText('Chat expiration')).toHaveAttribute('dateTime', renewedExpiration));
  });

  it('reports an expired stored chat and requires a new conversation', async () => {
    const user = userEvent.setup();
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'expired-session',
      endpoint: '/ai',
      expiresAt: Date.now() - 1,
      retentionSeconds: 172800,
      messages: [{ id: 'user-1', role: 'user', content: 'Old question' }],
      syncedScheduleSpec: 'description: old schedule\n',
    }));

    render(<ExperimentalAiPage />);

    expect(await screen.findByText('Old question')).toBeInTheDocument();
    expect(screen.getByText(/expired after 2 days of inactivity/)).toBeInTheDocument();
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    expect(composer).toBeEnabled();
    await user.type(composer, 'Draft for a new chat');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }));
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(composer).toHaveValue('Draft for a new chat');
    expect(mockGetSessionStatus).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem('nurse-scheduling-ai-conversation')).toBeNull();
  });

  it('keeps a thirty-day chat through the browser timer limit until its real expiry', async () => {
    vi.useFakeTimers();
    try {
      const now = Date.parse('2026-09-19T08:30:00Z');
      vi.setSystemTime(now);
      mockGetSessionStatus.mockResolvedValue(2592000);
      mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, session_retention_seconds: 2592000 });
      window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
        sessionId: 'long-session', endpoint: '/ai', expiresAt: now + 2592000 * 1000,
        retentionSeconds: 2592000, messages: [{ id: 'user-1', role: 'user', content: 'Keep this chat' }],
        syncedScheduleSpec: 'description: old schedule\n',
      }));
      render(<ExperimentalAiPage />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getByLabelText('Chat expiration')).toBeInTheDocument();
      // Browser timers cannot wait the whole period at once, so the page checks again after each wake.
      await act(async () => { await vi.advanceTimersByTimeAsync(2147483647); });
      expect(screen.queryByText(/This chat expired/)).not.toBeInTheDocument();
      expect(screen.getByLabelText('Chat expiration')).toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(2592000 * 1000 - 2147483647 - 1); });
      expect(screen.queryByText(/This chat expired/)).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      expect(screen.getByText(/This chat expired after 30 days/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('reattaches a restored request to its run with the same message ID', async () => {
    const modelSelection = { model: 'deep', reasoning: 'high' };
    const costSummary = { usd: '0.1', calls: 1, pending: 0, unavailable: 0 };
    const providerCalls = [{ callId: 'paid-call', model: 'deep', reasoning: 'high', status: 'reported',
      costUsd: '0.1', providerCallId: 'gateway-id', responseModel: null, usage: null }];
    const pendingRequest = {
      messageId: 'original-request', question: 'Keep working', questionId: 'question', assistantId: 'answer',
      createdAt: Date.now() - 1000, uploading: false,
    };
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session', endpoint: '/ai', expiresAt: Date.now() + 60_000, retentionSeconds: 2592000,
      messages: [
        { id: 'question', role: 'user', content: pendingRequest.question },
        { id: 'answer', role: 'assistant', content: 'Partial', status: 'pending',
          activity: [{ kind: 'response', text: 'Partial' }], modelSelection, costSummary, providerCalls },
      ],
      syncedScheduleSpec: 'description: original schedule\n', sessionEventId: 4, pendingRequest,
    }));
    mockRunEvents.mockImplementation(async (_sessionId: string, _message: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'delta', text: ' and finished.' });
    });
    render(<ExperimentalAiPage />);

    await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Partial and finished.')).toBeInTheDocument();
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    expect(mockSendMessage.mock.calls[0][0]).toBe('restored-session');
    expect(mockSendMessage.mock.calls[0][1]).toBe('Keep working');
    expect(mockSendMessage.mock.calls[0][5]).toMatchObject({ messageId: 'original-request' });
    // The accepted run used the original schedule, so recovery neither creates nor updates a session.
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
    expect(mockStreamSessionEvents.mock.calls[0][1].lastEventId).toBe(4);
    expect(screen.getAllByText('Keep working')).toHaveLength(1);
    await waitFor(() => {
      const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
      expect(stored.pendingRequest).toBeNull();
    });
    const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    expect(stored.messages.find((message: { id: string }) => message.id === 'answer')).toMatchObject({
      modelSelection, costSummary, providerCalls,
    });
  });

  it('uses a singular retention label for a one-hour session', async () => {
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'expired-session',
      endpoint: '/ai',
      expiresAt: Date.now() - 1,
      retentionSeconds: 3600,
      messages: [{ id: 'user-1', role: 'user', content: 'Old question' }],
      syncedScheduleSpec: 'description: old schedule\n',
    }));

    render(<ExperimentalAiPage />);

    expect(await screen.findByText(/expired after 1 hour of inactivity/)).toBeInTheDocument();
    expect(screen.queryByText(/1 hours/)).not.toBeInTheDocument();
  });

  it('preserves the transcript when the stored server session is no longer available', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockGetSessionStatus.mockRejectedValue(new MockAiHttpError('Chat session not found.', 404));
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'missing-session',
      endpoint: '/ai',
      expiresAt: Date.now() + 60_000,
      retentionSeconds: 172800,
      messages: [{ id: 'user-1', role: 'user', content: 'Preserve this transcript' }],
      syncedScheduleSpec: 'description: old schedule\n',
    }));

    render(<ExperimentalAiPage />);

    expect(await screen.findByText(/no longer available on the AI server/)).toBeInTheDocument();
    expect(screen.getByText('Preserve this transcript')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Start new chat' }));
    expect(screen.queryByText('Preserve this transcript')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
    expect(window.sessionStorage.getItem('nurse-scheduling-ai-conversation')).toBeNull();
  });

  it('reports a failed restored-session check and retries after credentials change', async () => {
    mockGetCapabilities.mockResolvedValueOnce({
      ...defaultCapabilities,
      auth: { required: true, scheme: 'bearer' },
    });
    mockGetSessionStatus
      .mockRejectedValueOnce(new Error('Temporary session-status failure.'))
      .mockResolvedValueOnce(3600);
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session',
      endpoint: '/ai',
      expiresAt: Date.now() + 60_000,
      retentionSeconds: 172800,
      messages: [{ id: 'user-1', role: 'user', content: 'Stored question' }],
      syncedScheduleSpec: 'description: old schedule\n',
    }));
    const user = userEvent.setup();

    render(<ExperimentalAiPage />);

    expect(await screen.findByText('Temporary session-status failure.')).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Enter token for AI assistant' }));
    await user.type(screen.getByLabelText('Token for AI assistant'), 'replacement-token');
    await user.click(screen.getByRole('button', { name: 'Save token for AI assistant' }));

    await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalledTimes(2));
    expect(mockGetSessionStatus).toHaveBeenLastCalledWith('restored-session', 'replacement-token', '/ai');
  });

  it('debounces streamed transcript writes and flushes the latest text on page hide', async () => {
    const user = userEvent.setup();
    let emit: SessionEventHandler | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      emit = callbacks.onEvent;
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(emit).toBeDefined());
    const writeConversation = vi.spyOn(Storage.prototype, 'setItem');

    act(() => emit?.({ type: 'delta', text: 'First' }));
    act(() => emit?.({ type: 'delta', text: ' second' }));
    expect(writeConversation).not.toHaveBeenCalled();

    act(() => window.dispatchEvent(new Event('pagehide')));
    const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    expect(stored.messages.at(-1).content).toBe('First second');
    expect(writeConversation.mock.calls.filter(([key]) => key === 'nurse-scheduling-ai-conversation')).toHaveLength(1);
    await act(async () => finishStream?.());
  });

  it('bounds the persisted optimizer progress history during a long run', async () => {
    const user = userEvent.setup();
    let backgroundCallbacks: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (
      _sessionId: string,
      callbacks: typeof backgroundCallbacks,
    ) => {
      backgroundCallbacks = callbacks;
      await new Promise<void>(() => {});
    });
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Optimize it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');

    act(() => {
      backgroundCallbacks?.onEvent({ type: 'optimization', activity: {
        jobId: 'opt-long-run',
        state: 'running',
        terminal: false,
        downloadable: false,
      } });
      for (let index = 0; index < 1200; index += 1) {
        backgroundCallbacks?.onEvent({ type: 'optimization_progress', activity: {
          jobId: 'opt-long-run', point: { currentBestScore: index, elapsedSeconds: index },
        } });
      }
    });
    act(() => window.dispatchEvent(new Event('pagehide')));

    const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    const points = stored.activeOptimization.points;
    expect(points.length).toBeLessThanOrEqual(500);
    // Decimation keeps the run's endpoints so the sparkline still spans the whole run.
    expect(points[0]).toEqual({ currentBestScore: 0, elapsedSeconds: 0 });
    expect(points.at(-1)).toEqual({ currentBestScore: 1199, elapsedSeconds: 1199 });
  });

  it('discards queued questions when the active conversation expires', async () => {
    const user = userEvent.setup();
    let rejectStream: ((reason: Error) => void) | undefined;
    mockSendMessage.mockImplementationOnce(async () => {
      return await new Promise<string>((_resolve, reject) => {
        rejectStream = reject;
      });
    });
    render(<ExperimentalAiPage />);
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });

    await user.type(composer, 'First question.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByRole('button', { name: 'Stop' });
    await user.type(composer, 'Do not resend this.');
    await user.keyboard('{Enter}');
    expect(screen.getByText('Queued for steering')).toBeInTheDocument();

    rejectStream?.(new MockAiHttpError('Chat session not found.', 404));

    expect(await screen.findByText(/expired or is no longer available/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Queued for steering')).not.toBeInTheDocument());
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
  });

  it('restores a remembered token for the same AI endpoint', async () => {
    window.localStorage.setItem('nurse-scheduling-ai-auth', JSON.stringify({
      endpoint: '/ai',
      token: 'remembered-ai-token',
    }));
    mockGetCapabilities.mockResolvedValueOnce({
      ...defaultCapabilities,
      auth: { required: true, scheme: 'bearer' },
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    expect(await screen.findByText('Token saved on this device')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(mockCreateSession).toHaveBeenCalledWith(
      'description: current Schedule Spec\n',
      'remembered-ai-token',
      '/ai',
      undefined,
    ));
  });
});
