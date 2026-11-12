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
  mockCancelOptimization,
  mockRunEvents,
  mockSendMessage,
  mockStreamSessionEvents,
  mockStopSession,
  mockGenerateYaml,
  mockQueueMessage,
  mockUseTabSwitchWarning,
  runEvents,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('sends a question with the current Schedule Spec and renders streamed text', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    // Generated export defaults are added only when the optimizer submits the schedule.
    expect(mockGenerateYaml.mock.calls[0][0]).not.toHaveProperty('export');

    expect(screen.getByText('Browser Schedule Spec: 0 people, 0 dates. Sent when you send a message.')).toBeInTheDocument();
    expect(screen.getByText(/^Frontend /)).toHaveTextContent('Frontend unknown');
    await waitFor(() => expect(screen.getByText(/^Backend(?:\s|$)/)).toHaveTextContent('Backend v0.4.3'));
    expect(screen.getByRole('link', { name: 'Experimental AI documentation' })).toHaveAttribute(
      'href',
      '/docs/user-guide/experimental-ai/',
    );
    expect(screen.getByRole('link', { name: 'Request beta access' })).toHaveAttribute(
      'href',
      'https://github.com/j3soon/nurse-scheduling#ai-beta-access',
    );
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute(
      'href',
      'https://github.com/j3soon/nurse-scheduling/blob/dev/PRIVACY.md',
    );
    expect(screen.queryByText(/When a response finishes/)).not.toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works Monday?');
    const sendButton = screen.getByRole('button', { name: 'Send' });
    expect(sendButton).toHaveTextContent('');
    expect(sendButton.querySelector('svg')).not.toBeNull();
    await user.click(sendButton);

    expect(await screen.findByText('Alice works Monday.')).toBeInTheDocument();
    const responseTime = screen.getByText(/· (?:<1s|\d+(?:\.\d)?s|\d+m \d+s)$/);
    expect(responseTime.tagName).toBe('TIME');
    expect(responseTime).toHaveAttribute('dateTime');
    expect(responseTime).toHaveAttribute('title', new Date(responseTime.getAttribute('dateTime')!).toLocaleString());
    const userTime = screen.getByText('Who works Monday?').closest('article')?.querySelector('time');
    expect(userTime).toHaveAttribute('title', new Date(userTime!.dateTime).toLocaleString());
    expect(mockCreateSession).toHaveBeenCalledWith('description: current Schedule Spec\n', null, '/ai', undefined);
    expect(mockRunEvents).toHaveBeenCalledWith(
      'session-id',
      'Who works Monday?',
      expect.any(Object),
      expect.any(AbortSignal),
      null,
      '/ai',
    );
    expect(mockUseTabSwitchWarning).toHaveBeenCalledWith(true);
    expect(mockUseTabSwitchWarning).toHaveBeenLastCalledWith(false);
  });

  it('allows switching app pages during a response', async () => {
    mockRunEvents.mockImplementation(() => new Promise<void>(() => {}));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Keep working');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('button', { name: 'Stop' })).toBeInTheDocument();
    // The server keeps the accepted run, and the restored page reattaches to it.
    expect(mockUseTabSwitchWarning).toHaveBeenLastCalledWith(false);
  });

  it('shows that a response continues while its request reconnects', async () => {
    let connectionChange: ((connected: boolean) => void) | undefined;
    mockSendMessage.mockImplementation(async (
      _id: string, _message: string, _signal: AbortSignal, _token: string | null, _endpoint: string,
      options: { onConnectionChange?: (connected: boolean) => void },
    ) => {
      connectionChange = options.onConnectionChange;
      return new Promise(() => {});
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Keep working');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(connectionChange).toBeDefined());

    act(() => connectionChange?.(false));
    expect(screen.getByText('Reconnecting. Your AI response continues on the server.')).toBeInTheDocument();
    act(() => connectionChange?.(true));
    expect(screen.queryByText('Reconnecting. Your AI response continues on the server.')).not.toBeInTheDocument();
  });

  it('keeps the optimizer visible after a cancel failure and allows a retry', async () => {
    const user = userEvent.setup();
    mockCancelOptimization.mockRejectedValueOnce(new Error('Optimizer unavailable.'));
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Optimize it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => stream.onEvent({ type: 'optimization', activity: {
      jobId: 'opt-1', state: 'running', terminal: false, downloadable: false,
    } }));
    await user.click(screen.getByRole('button', { name: 'Cancel optimizer' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Optimizer unavailable.');
    await user.click(screen.getByRole('button', { name: 'Cancel optimizer' }));
    expect(mockCancelOptimization).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Cancelling optimizer…' })).toBeDisabled();
  });

  it('reissues Stop after message acceptance when the first Stop reached the server too early', async () => {
    const user = userEvent.setup();
    let accept: ((id: string) => void) | undefined;
    mockSendMessage.mockImplementationOnce(() => new Promise<string>(resolve => { accept = resolve; }));
    mockStopSession.mockResolvedValue(undefined);
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Wait');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(accept).toBeDefined());
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(mockStopSession).toHaveBeenCalledOnce();
    const signal = mockSendMessage.mock.calls[0][2] as AbortSignal;
    expect(signal.aborted).toBe(false);
    await act(async () => accept?.('accepted'));
    await waitFor(() => expect(mockStopSession).toHaveBeenCalledTimes(2));
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => runEvents(stream, 'accepted')?.onEvent({ type: 'stopped', runId: 'accepted' }));
    expect(await screen.findByText('Stopped before completion.')).toBeInTheDocument();
  });

  it('shows automatic provider retries as notices without a retry button', async () => {
    const user = userEvent.setup();
    let callbacks: SessionStreamOptions | undefined;
    let finish: (() => void) | undefined;
    mockRunEvents.mockImplementation(async (_id: string, _question: string, stream: SessionStreamOptions) => {
      callbacks = stream;
      stream.onEvent({ type: 'tool', activity: { name: 'bash', arguments: '{}', result: 'Completed once', ok: true } });
      stream.onEvent({ type: 'provider_retry', message: 'The provider timed out. Retrying in 2 s (attempt 2 of 5).' });
      await new Promise<void>(resolve => { finish = resolve; });
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Build a schedule.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('The provider timed out. Retrying in 2 s (attempt 2 of 5).')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    act(() => callbacks?.onEvent({ type: 'delta', text: 'Recovered output.' }));
    expect(screen.getByText('Recovered output.')).toBeInTheDocument();
    expect(screen.getByText('Completed once')).toBeInTheDocument();
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    await act(async () => finish?.());
  });

  it('delivers queued steering during optimizer review without sending it again', async () => {
    const user = userEvent.setup();
    let background: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (_id: string, callbacks: SessionStreamOptions) => {
      background = callbacks;
      await new Promise<void>(() => {});
    });
    render(<ExperimentalAiPage />);
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    await user.type(composer, 'Optimize it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    act(() => background?.onEvent({ type: 'run_start', runId: 'review', trigger: 'optimizer' }));
    await user.type(composer, 'Check night coverage first.');
    await user.click(screen.getByRole('button', { name: 'Queue message' }));
    const queuedId = mockQueueMessage.mock.calls[0][1] as string;
    expect(screen.getByText('Queued for steering')).toBeInTheDocument();
    act(() => {
      background?.onEvent({ type: 'tool', runId: 'review', activity: { name: 'read', arguments: '{}', result: 'Read complete', ok: true } });
      background?.onEvent({ type: 'steering', runId: 'review', messageId: queuedId, message: 'Check night coverage first.' });
      background?.onEvent({ type: 'delta', runId: 'review', text: 'Night coverage checked.' });
    });
    expect(screen.queryByText('Queued for steering')).not.toBeInTheDocument();
    expect(screen.getByText('Check night coverage first.')).toBeInTheDocument();
    expect(screen.getByText('Night coverage checked.')).toBeInTheDocument();
    act(() => background?.onEvent({ type: 'done', runId: 'review' }));
    await screen.findByRole('button', { name: 'Send' });
    expect(mockRunEvents).toHaveBeenCalledTimes(1);
  });

  it('re-enables Stop when the stop request itself fails', async () => {
    const user = userEvent.setup();
    mockStopSession.mockRejectedValue(new Error('network down'));
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
    act(() => backgroundCallbacks?.onEvent({ type: 'run_start', runId: 'optimizer-turn', trigger: 'optimizer' }));

    await user.click(screen.getByRole('button', { name: 'Stop' }));
    await act(async () => {});

    // The run is still active, so the user has to be able to ask again.
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
  });

  it('stops the active response through the session endpoint and keeps its partial output', async () => {
    const user = userEvent.setup();
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
      signal: AbortSignal,
    ) => {
      callbacks.onEvent({ type: 'delta', text: 'Partial answer.' });
      callbacks.onEvent({ type: 'tool_start', activity: { toolCallId: 'call-1', name: 'bash', arguments: '{"command":"sleep 60"}' } });
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      });
    });
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Keep working.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Partial answer.');
    await user.click(await screen.findByRole('button', { name: 'Stop' }));

    // The Stop names its message, so it cannot end a later run.
    expect(mockStopSession).toHaveBeenCalledWith('session-id', null, '/ai', expect.any(String));
    expect(await screen.findByText('Stopped before completion.')).toBeInTheDocument();
    expect(screen.getByText('Partial answer.')).toBeInTheDocument();
    expect(screen.getByText('bash · interrupted')).toBeInTheDocument();
    expect(screen.queryByText('Stopped.')).not.toBeInTheDocument();
    expect(screen.queryByText(/failed before completion/)).not.toBeInTheDocument();
  });

  it('queues a drafted question while a response is streaming', async () => {
    const user = userEvent.setup();
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async () => {
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    render(<ExperimentalAiPage />);
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });

    await user.type(composer, 'First question.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByRole('button', { name: 'Stop' });

    expect(composer).toBeEnabled();
    await user.type(composer, 'Next question.');
    await user.keyboard('{Enter}');
    expect(mockRunEvents).toHaveBeenCalledTimes(1);
    expect(composer).toHaveValue('');
    expect(screen.getByText('Queued for steering')).toBeInTheDocument();
    expect(mockQueueMessage).toHaveBeenCalledWith(
      'session-id',
      expect.any(String),
      'Next question.',
      null,
      '/ai',
    );

    finishStream?.();
    await screen.findByRole('button', { name: 'Send' });
    await waitFor(() => expect(mockRunEvents).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('shows backend failures and continues with a new message', async () => {
    const providerError = 'The AI provider returned HTTP 525. Error ID: 72dc8f31-45af-410d-9fc2-41bdf1fc718f.';
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      callbacks.onEvent({ type: 'delta', text: 'Provisional response.' });
      throw new Error(providerError);
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Can you help?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(providerError);
    expect(screen.getByText('Can you help?')).toBeInTheDocument();
    expect(screen.getByText('Provisional response.')).toBeInTheDocument();
    expect(screen.getByText('This response failed before completion. Send a new message to continue.')).toBeInTheDocument();
    expect(screen.getByText('Provisional response.').closest('article')).toHaveTextContent(providerError);
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Continue');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Alice works Monday.')).toBeInTheDocument();
    expect(mockRunEvents).toHaveBeenCalledTimes(2);
    expect(mockRunEvents.mock.calls[1][1]).toBe('Continue');
    // The failed response stays in the chat above the new question.
    expect(screen.getByText('Provisional response.')).toBeInTheDocument();
    expect(screen.getByText('This response failed before completion. Send a new message to continue.')).toBeInTheDocument();
  });
});
