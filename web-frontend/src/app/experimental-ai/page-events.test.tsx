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
  mockDownloadOptimization,
  mockCancelOptimization,
  mockGetCapabilities,
  mockRunEvents,
  mockSendMessage,
  mockStreamSessionEvents,
  mockStopSession,
  mockQueueMessage,
  mockUpdateSessionSchedule,
  MockAiHttpError,
  defaultCapabilities,
  runEvents,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('renews a reconnected background run with the current retention period', async () => {
    let resolveCapabilities!: (value: typeof defaultCapabilities) => void;
    mockGetCapabilities.mockImplementation(() => new Promise(resolve => { resolveCapabilities = resolve; }));
    const readers: { callbacks: SessionStreamOptions; end: () => void }[] = [];
    mockStreamSessionEvents.mockImplementation((_id, callbacks) => new Promise<void>(resolve => {
      readers.push({ callbacks, end: resolve });
    }));
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'session-id', endpoint: '/ai', expiresAt: Date.now() + 300000,
      retentionSeconds: 10, messages: [], syncedScheduleSpec: 'description: current Schedule Spec\n',
    }));
    render(<ExperimentalAiPage />);
    await waitFor(() => expect(readers).toHaveLength(1));
    await act(async () => resolveCapabilities({ ...defaultCapabilities, session_retention_seconds: 100 }));
    readers[0].end();
    await waitFor(() => expect(readers).toHaveLength(2), { timeout: 4000 });
    const started = Date.now();
    act(() => readers[1].callbacks.onEvent({ type: 'run_start', runId: 'background-run', trigger: 'optimization' }));
    await waitFor(() => {
      const saved = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation')!);
      expect(saved.messages.some((message: { id: string }) => message.id === 'background-run')).toBe(true);
      expect(saved.retentionSeconds).toBe(100);
      expect(saved.expiresAt).toBeGreaterThanOrEqual(started + 99000);
    });
  });

  it('ends a restored background reply when its chat has expired', async () => {
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'expired-session',
      endpoint: '/ai',
      expiresAt: Date.now() - 1,
      retentionSeconds: 172800,
      messages: [{ id: 'optimizer-turn', role: 'assistant', content: 'Partial ', status: 'pending' }],
      syncedScheduleSpec: 'description: old schedule\n',
      backgroundAssistantId: 'optimizer-turn',
    }));

    render(<ExperimentalAiPage />);

    expect(await screen.findByText(/expired after 2 days of inactivity/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start new chat' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it.each([
    { steeringCount: 1, replacement: false }, { steeringCount: 2, replacement: false },
    { steeringCount: 1, replacement: true }, { steeringCount: 2, replacement: true },
  ])('restores the active reply after $steeringCount steering messages, replacement=$replacement', async ({ steeringCount, replacement }) => {
    const modelSelection = { model: 'deep', reasoning: 'high' };
    let callbacks: SessionStreamOptions | undefined;
    mockRunEvents.mockImplementation(async (_session: string, _question: string, target: SessionStreamOptions) => {
      callbacks = target;
      target.onEvent({ type: 'model_selection', selection: modelSelection });
      target.onEvent({ type: 'delta', text: 'Original answer.' });
      await new Promise<void>(() => {});
    });
    const user = userEvent.setup();
    const view = render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Explain coverage.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Original answer.');
    await act(async () => {
      for (let index = 1; index <= steeringCount; index++) {
        callbacks?.onEvent({ type: 'steering', messageId: `queued-${index}`, message: `Compare day ${index}.` });
        callbacks?.onEvent({ type: 'delta', text: `Day ${index} partial` });
      }
      const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
      stream.onEventId?.(10);
    });
    act(() => window.dispatchEvent(new Event('pagehide')));
    const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    const activeId = stored.messages.at(-1).id;
    const messageId = mockSendMessage.mock.calls[0][5].messageId;
    expect(stored.pendingRequest).toMatchObject({ messageId, activeAssistantId: activeId });
    expect(stored.messages.at(-1).requestId).toBe(messageId);
    expect(stored.messages.filter((message: { role: string }) => message.role === 'assistant')
      .map((message: { modelSelection: object }) => message.modelSelection)).toEqual(
      Array.from({ length: steeringCount + 1 }, () => modelSelection),
    );
    expect(stored.messages.find((message: { id: string }) => message.id === `queued-${steeringCount}`).requestId).toBe(messageId);

    await act(async () => view.unmount());
    mockSendMessage.mockClear();
    mockCreateSession.mockClear();
    mockUpdateSessionSchedule.mockClear();
    mockRunEvents.mockImplementation(async (_session: string, _question: string, target: SessionStreamOptions) => {
      if (replacement) {
        target.onEvent({ type: 'session_reset', reset: {
          runIds: ['user-run-1'], activeRunId: 'user-run-1', terminalRunIds: [], incomplete: false,
        } });
        target.onEvent({ type: 'model_selection', selection: modelSelection });
        target.onEvent({ type: 'delta', text: 'Original answer.' });
        for (let index = 1; index <= steeringCount; index++) {
          target.onEvent({ type: 'steering', messageId: `queued-${index}`, message: `Compare day ${index}.` });
          target.onEvent({ type: 'delta', text: `Day ${index} partial` });
        }
      }
      target.onEvent({ type: 'delta', text: ' and finished.' });
    });
    render(<ExperimentalAiPage />);

    await screen.findByText(`Day ${steeringCount} partial and finished.`);
    expect(screen.getAllByText('Original answer.')).toHaveLength(1);
    for (let index = 1; index <= steeringCount; index++) {
      expect(screen.getAllByText(`Compare day ${index}.`)).toHaveLength(1);
    }
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    expect(mockSendMessage.mock.calls[0][5]).toMatchObject({ messageId });
    expect(mockStreamSessionEvents.mock.calls.at(-1)![1].lastEventId).toBe(10);
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
    await waitFor(() => {
      const completed = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
      expect(completed.pendingRequest).toBeNull();
      if (!replacement) expect(completed.messages.find((message: { id: string }) => message.id === activeId).status).toBeUndefined();
      expect(completed.messages.some((message: { status?: string }) => message.status === 'pending')).toBe(false);
      expect(completed.messages.filter((message: { role: string }) => message.role === 'assistant')
        .map((message: { modelSelection: object }) => message.modelSelection)).toEqual(
        Array.from({ length: steeringCount + 1 }, () => modelSelection),
      );
      expect(completed.messages.map((message: { role: string; content: string }) => [message.role, message.content])).toEqual([
        ['user', 'Explain coverage.'], ['assistant', 'Original answer.'],
        ...Array.from({ length: steeringCount }, (_, index) => [
          ['user', `Compare day ${index + 1}.`],
          ['assistant', `Day ${index + 1} partial${index + 1 === steeringCount ? ' and finished.' : ''}`],
        ]).flat(),
      ]);
    });
  });

  it('shows request messages as role bubbles in the order the model receives them', async () => {
    let turn = 0;
    mockRunEvents.mockImplementation(async (_sessionId: string, message: string, callbacks: SessionStreamOptions) => {
      turn += 1;
      callbacks.onEvent({ type: 'model_input', input: {
        system: 'Shared system prompt',
        messages: [
          // The second run repeats the event, as after a failed run. The page shows it once.
          { kind: 'app', index: 0, content: '[App event] The user uploaded files: ward.csv', title: 'Files Uploaded' },
          { kind: 'question', content: message },
          { kind: 'status', content: `[Current status]\nTurn ${turn}`, title: 'Current Time' },
        ],
      } });
      callbacks.onEvent({ type: 'delta', text: `Answer to ${message}` });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });

    await user.type(composer, 'First');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Answer to First');
    await user.type(composer, 'Second');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Answer to Second');

    const cards = Array.from(screen.getByLabelText('Chat messages').querySelectorAll('article'));
    // Earlier status messages remain visible because they stay in model context.
    expect(cards.map(card => card.querySelector('p')?.textContent)).toEqual([
      'System', 'User · App - Files Uploaded', 'User', 'User · Status - Current Time', 'Assistant', 'User', 'User · Status - Current Time', 'Assistant',
    ]);
    // The label names the topic, so the exact text of app and status messages starts collapsed.
    for (const [card, text] of [[cards[1], '[App event] The user uploaded files: ward.csv'], [cards[6], 'Turn 2']] as const) {
      expect(card.querySelector('details')).not.toHaveAttribute('open');
      expect(card.querySelector('details pre')).toHaveTextContent(text);
    }
    const systemPrompt = cards[0].querySelector('details');
    expect(systemPrompt).not.toHaveAttribute('open');
    expect(systemPrompt).toHaveTextContent('Shared system prompt');
  });

  it('renders an assistant turn when background optimization wakes the agent', async () => {
    const user = userEvent.setup();
    let backgroundCallbacks: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (
      _sessionId: string,
      callbacks: typeof backgroundCallbacks,
    ) => {
      backgroundCallbacks = callbacks;
      await new Promise<void>(() => {});
    });
    const firstRender = render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Optimize it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');

    act(() => backgroundCallbacks?.onEvent({ type: 'optimization', activity: {
      jobId: 'opt-result-1',
      state: 'running',
      terminal: false,
      downloadable: false,
    } }));
    expect(screen.getAllByRole('status').find(status => status.textContent?.includes('Optimizer running in the background'))).toHaveTextContent('Optimizer running in the background · running');

    act(() => {
      backgroundCallbacks?.onEvent({ type: 'optimization_progress', activity: {
        jobId: 'opt-result-1', point: { currentBestScore: 12, elapsedSeconds: 1 },
      } });
      backgroundCallbacks?.onEvent({ type: 'optimization_progress', activity: {
        jobId: 'opt-result-1', point: { currentBestScore: 23, elapsedSeconds: 2 },
      } });
    });
    expect(screen.getByText('Score 23')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Optimization score trend' })).toBeInTheDocument();

    act(() => {
      backgroundCallbacks?.onEvent({ type: 'optimization', activity: {
        jobId: 'opt-result-1',
        state: 'completed',
        terminal: true,
        downloadable: true,
        result: { outcome: 'optimal', score: 0, solverStatus: 'OPTIMAL', terminationReason: 'completed' },
        error: { code: 'backend-error', message: 'Failed\nOutcome: injected\r\nBackend version: forged' },
        request: { solver: 'ortools/cp-sat', timeoutSeconds: 300 },
        backend: { url: 'http://optimizer:8000', appVersion: 'v0.4.3', requestTimeoutSeconds: 30,
          claimedPerformance: { score: 125, appVersion: 'v0.4.2', measuredAt: '2026-09-18T01:00:00Z' } },
      } });
      backgroundCallbacks?.onEvent({ type: 'run_start', runId: 'optimizer-turn', trigger: 'optimizer' });
      backgroundCallbacks?.onEvent({ type: 'model_input', input: {
        system: 'Background system prompt',
        messages: [
          { kind: 'optimizer', content: 'Optimizer result with score 23.' },
          { kind: 'status', content: '[Current status]\nOptimization result: result.xlsx.' },
        ],
      } });
      backgroundCallbacks?.onEvent({ type: 'tool_start', activity: { name: 'bash', arguments: '{"command":"echo ready"}' } });
    });
    const optimizerInput = screen.getByText('Optimizer result with score 23.').closest('article');
    expect(optimizerInput?.querySelector('p')).toHaveTextContent('User · Optimizer');
    expect(optimizerInput).toHaveClass('ml-auto');
    expect(optimizerInput?.previousElementSibling).toHaveTextContent('Background system prompt');
    expect(optimizerInput?.nextElementSibling).toHaveTextContent('Optimization result: result.xlsx.');
    // Background tools stay in message activity. The status area is reserved for optimizer jobs.
    expect(screen.queryByText('Background tool running · bash')).not.toBeInTheDocument();
    expect(screen.getByText('bash · running')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Show tool activity' }));
    expect(screen.queryByText('Background tool running · bash')).not.toBeInTheDocument();
    expect(screen.queryByText('bash · running')).not.toBeInTheDocument();

    act(() => {
      backgroundCallbacks?.onEvent({ type: 'tool', activity: { name: 'bash', arguments: '{"command":"echo ready"}', result: 'ready', ok: true } });
      backgroundCallbacks?.onEvent({ type: 'delta', text: 'The optimizer returned score 23.' });
      backgroundCallbacks?.onEvent({ type: 'done' });
      backgroundCallbacks?.onEventId?.(4);
    });

    expect(screen.queryByText('Background tool running · bash')).not.toBeInTheDocument();
    expect(screen.queryByText(/Optimizer running in the background/)).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Optimization score trend' })).not.toBeInTheDocument();
    const optimizerSummary = screen.getByText(/^Optimization finished\. Download/).closest('article')!;
    expect(optimizerSummary).toHaveTextContent('Outcome: optimal');
    expect(optimizerSummary).toHaveTextContent('Final score: 0');
    expect(optimizerSummary).toHaveTextContent('Backend URL: http://optimizer:8000');
    expect(optimizerSummary).toHaveTextContent('Backend version: v0.4.3');
    expect(optimizerSummary).toHaveTextContent('Solver timeout: 300s');
    expect(optimizerSummary).toHaveTextContent('Backend request timeout: 30s');
    expect(optimizerSummary).toHaveTextContent('Claimed performance: 125');
    expect(screen.getAllByText('Outcome:')).toHaveLength(1);
    expect(screen.getAllByText('Backend version:')).toHaveLength(1);
    expect(screen.getByText('Error:').nextElementSibling?.textContent).toBe(
      'Failed\nOutcome: injected\nBackend version: forged',
    );
    expect(screen.getByText('Final score:').tagName).toBe('DT');
    expect(screen.getByText('Final score:')).toHaveClass('optimizer-label');
    expect(optimizerSummary.querySelector('time')).toHaveAttribute('title');
    const createObjectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:optimizer-result');
    const revokeObjectUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const clickDownload = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    await user.click(screen.getByRole('button', { name: 'Download schedule' }));
    await waitFor(() => expect(mockDownloadOptimization).toHaveBeenCalledWith(
      'session-id',
      'opt-result-1',
      null,
      '/ai',
    ));
    expect(createObjectUrl).toHaveBeenCalled();
    expect(clickDownload).toHaveBeenCalled();
    expect(revokeObjectUrl).not.toHaveBeenCalledWith('blob:optimizer-result');
    expect(screen.getByText('The optimizer returned score 23.')).toBeInTheDocument();
    expect(mockStreamSessionEvents).toHaveBeenCalledWith(
      'session-id',
      expect.any(Object),
      expect.any(AbortSignal),
      null,
      '/ai',
    );
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Thanks');
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
    await waitFor(() => {
      const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
      expect(stored.messages).toEqual(expect.arrayContaining([
        expect.objectContaining({ role: 'optimizer', optimizerJob: { jobId: 'opt-result-1', downloadable: true } }),
      ]));
    });
    firstRender.unmount();
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:optimizer-result');
    render(<ExperimentalAiPage />);
    expect(await screen.findByRole('button', { name: 'Download schedule' })).toBeInTheDocument();
    expect(screen.getAllByText('The optimizer returned score 23.')).toHaveLength(1);
    expect(mockStreamSessionEvents.mock.calls.at(-1)?.[1].lastEventId).toBe(4);
  });

  it('cancels the background optimizer directly while a chat response continues', async () => {
    const user = userEvent.setup();
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async () => {
      await new Promise<void>(resolve => { finishStream = resolve; });
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Optimize it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(finishStream).toBeDefined());
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => stream.onEvent({ type: 'optimization', activity: {
      jobId: 'opt-1', state: 'running', terminal: false, downloadable: false,
    } }));
    await user.click(screen.getByRole('button', { name: 'Cancel optimizer' }));

    expect(mockCancelOptimization).toHaveBeenCalledExactlyOnceWith('session-id', 'opt-1', null, '/ai');
    expect(screen.getByRole('button', { name: 'Cancelling optimizer…' })).toBeDisabled();
    expect(mockStopSession).not.toHaveBeenCalled();
    expect(mockQueueMessage).not.toHaveBeenCalled();
    expect(mockRunEvents).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();

    act(() => stream.onEvent({ type: 'optimization', activity: {
      jobId: 'opt-1', state: 'cancelled', terminal: true, downloadable: false,
    } }));
    expect(screen.queryByText(/Optimizer running in the background/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    await act(async () => finishStream?.());
  });

  it('reopens the background event stream after it disconnects', async () => {
    const user = userEvent.setup();
    mockStreamSessionEvents
      .mockImplementationOnce(async (_sessionId: string, callbacks: { onEventId?: (id: number) => void }) => {
        callbacks.onEventId?.(7);
        throw new Error('network down');
      })
      .mockImplementation(() => new Promise(() => undefined));
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Optimize it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    // Reconnection continues in the background, so the disconnect is not reported as an error.
    await waitFor(() => expect(mockStreamSessionEvents).toHaveBeenCalledTimes(2), { timeout: 4000 });
    expect(screen.queryByText('network down')).not.toBeInTheDocument();
    expect(mockStreamSessionEvents.mock.calls[1][0]).toBe('session-id');
    expect(mockStreamSessionEvents.mock.calls[1][1].lastEventId).toBe(7);
  });

  it('renders a replayed background turn that lost its start event', async () => {
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

    // The bounded replay buffer dropped run_start before this reconnect.
    act(() => {
      backgroundCallbacks?.onEvent({ type: 'delta', text: 'The optimizer returned score 23.' });
      backgroundCallbacks?.onEvent({ type: 'done' });
    });

    expect(screen.getByText('The optimizer returned score 23.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it('ends a stale background turn instead of leaving it pending', async () => {
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
      backgroundCallbacks?.onEvent({ type: 'run_start', runId: 'optimizer-turn', trigger: 'optimizer' });
      backgroundCallbacks?.onEvent({ type: 'delta', text: 'Obsolete partial answer.' });
      backgroundCallbacks?.onEvent({ type: 'stale', message: 'The Schedule Spec changed while this response was generated.' });
    });

    expect(screen.getByRole('alert')).toHaveTextContent('The Schedule Spec changed while this response was generated.');
    expect(screen.queryByText('Obsolete partial answer.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it.each(['done', 'stopped'] as const)('reconciles a replayed %s event with a restored background message', async event => {
    let backgroundCallbacks: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (
      _sessionId: string,
      callbacks: typeof backgroundCallbacks,
    ) => {
      backgroundCallbacks = callbacks;
      await new Promise<void>(() => {});
    });
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session',
      endpoint: '/ai',
      expiresAt: Date.now() + 60_000,
      retentionSeconds: 172800,
      messages: [{ id: 'optimizer-turn', role: 'assistant', content: 'Completed answer.', status: 'pending' }],
      syncedScheduleSpec: 'description: current Schedule Spec\n',
      sessionEventId: 4,
    }));

    render(<ExperimentalAiPage />);
    await waitFor(() => expect(backgroundCallbacks).toBeDefined());
    act(() => {
      if (event === 'done') backgroundCallbacks?.onEvent({ type: 'done', runId: 'optimizer-turn' });
      else backgroundCallbacks?.onEvent({ type: 'stopped', runId: 'optimizer-turn' });
    });
    act(() => window.dispatchEvent(new Event('pagehide')));

    const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    expect(stored.messages[0]).toEqual(expect.objectContaining({
      id: 'optimizer-turn',
      content: 'Completed answer.',
      responseCompletedAt: expect.any(Number),
    }));
    expect(stored.messages[0].status).toBe(event === 'done' ? undefined : 'stopped');
  });

  it('continues a restored background message when replay resumes without a turn start', async () => {
    let backgroundCallbacks: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (
      _sessionId: string,
      callbacks: typeof backgroundCallbacks,
    ) => {
      backgroundCallbacks = callbacks;
      await new Promise<void>(() => {});
    });
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session',
      endpoint: '/ai',
      expiresAt: Date.now() + 60_000,
      retentionSeconds: 172800,
      messages: [{ id: 'optimizer-turn', role: 'assistant', content: 'Partial ', status: 'pending' }],
      syncedScheduleSpec: 'description: current Schedule Spec\n',
      sessionEventId: 4,
      backgroundAssistantId: 'optimizer-turn',
    }));

    render(<ExperimentalAiPage />);
    await waitFor(() => expect(backgroundCallbacks).toBeDefined());
    act(() => backgroundCallbacks?.onEvent({ type: 'delta', text: 'answer.' }));
    act(() => backgroundCallbacks?.onEvent({ type: 'done', runId: 'optimizer-turn' }));
    act(() => window.dispatchEvent(new Event('pagehide')));

    const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    expect(stored.messages).toHaveLength(1);
    expect(stored.messages[0]).toEqual(expect.objectContaining({
      id: 'optimizer-turn',
      content: 'Partial answer.',
    }));
    expect(stored.messages[0].status).toBeUndefined();
  });

  it('keeps deferred review events when their reader disconnects before foreground message acceptance is acknowledged', async () => {
    const user = userEvent.setup();
    let disconnect: (() => void) | undefined;
    let accept: ((id: string) => void) | undefined;
    mockStreamSessionEvents.mockImplementationOnce(() => new Promise<void>(resolve => { disconnect = resolve; }));
    mockSendMessage.mockImplementationOnce(() => new Promise<string>(resolve => { accept = resolve; }));
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Wait');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(accept).toBeDefined());
    const stream = mockStreamSessionEvents.mock.calls[0][1] as SessionStreamOptions;
    act(() => {
      const review = runEvents(stream, 'review');
      review?.onEvent({ type: 'run_start', runId: 'review', trigger: 'optimizer' });
      review?.onEvent({ type: 'delta', text: 'Earlier review.' });
      review?.onEvent({ type: 'done', runId: 'review' });
      stream.onEventId?.(3);
      disconnect?.();
    });
    await waitFor(() => expect(mockStreamSessionEvents).toHaveBeenCalledTimes(2), { timeout: 4000 });
    await act(async () => accept?.('accepted'));
    expect(screen.getByText('Earlier review.')).toBeInTheDocument();
    const next = mockStreamSessionEvents.mock.calls[1][1] as SessionStreamOptions;
    act(() => {
      runEvents(next, 'accepted')?.onEvent({ type: 'delta', text: 'Current answer.' });
      runEvents(next, 'accepted')?.onEvent({ type: 'done', runId: 'accepted' });
    });
    expect(await screen.findByText('Current answer.')).toBeInTheDocument();
  });

  it('routes a terminal event received before the message acknowledgement to its foreground answer', async () => {
    const user = userEvent.setup();
    mockSendMessage.mockImplementationOnce(async () => {
      const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
      const previous = runEvents(stream, 'previous')!;
      previous.onEvent({ type: 'run_start', runId: 'previous', trigger: 'optimizer' });
      previous.onEvent({ type: 'delta', text: 'Previous review.' });
      previous.onEvent({ type: 'done', runId: 'previous' });
      const foreground = runEvents(stream, 'accepted')!;
      foreground.onEvent({ type: 'delta', text: 'Fast answer.' });
      foreground.onEvent({ type: 'done', runId: 'accepted' });
      return 'accepted';
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Explain');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Fast answer.')).toBeInTheDocument();
    expect(screen.getByText('Previous review.')).toBeInTheDocument();
    expect(screen.getAllByText('Fast answer.')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it('rebuilds matching foreground output from recovery without repeating its partial answer', async () => {
    const user = userEvent.setup();
    let callbacks: SessionStreamOptions | undefined;
    mockRunEvents.mockImplementationOnce(async (_id, _message, target) => {
      callbacks = target;
      target.onEvent({ type: 'delta', text: 'Partial' });
      await new Promise<void>(() => {});
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Explain');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Partial');
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    const reset = { runIds: ['user-run-1'], activeRunId: 'user-run-1', terminalRunIds: [], incomplete: false };
    act(() => {
      stream.onEvent({ type: 'session_reset', reset });
      callbacks?.onEvent({ type: 'delta', text: 'Partial answer recovered.' });
      callbacks?.onEvent({ type: 'steering', messageId: 'recovered-input', message: 'Focus on Tuesday.' });
      callbacks?.onEvent({ type: 'delta', text: 'Tuesday recovered.' });
      callbacks?.onEvent({ type: 'done', runId: 'user-run-1' });
    });
    expect(await screen.findByText('Partial answer recovered.')).toBeInTheDocument();
    expect(screen.queryByText('Partial')).not.toBeInTheDocument();
    expect(screen.getByText('Focus on Tuesday.')).toBeInTheDocument();
    expect(screen.getByText('Tuesday recovered.')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
  });

  it.each([false, true])('keeps replayed steering replies before later optimizer output, with an active run=%s', async active => {
    if (active) {
      mockRunEvents.mockImplementation(async (_session: string, _question: string, callbacks: SessionStreamOptions) => {
        callbacks.onEvent({ type: 'delta', text: 'Alice works Monday.' });
        await new Promise<void>(() => {});
      });
    }
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Explain');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    if (!active) await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    await act(async () => {
      stream.onEvent({ type: 'optimization', activity: { jobId: 'result', state: 'completed', terminal: true, downloadable: false } });
      stream.onEvent({ type: 'session_reset', reset: { runIds: ['user-run-1'], activeRunId: active ? 'user-run-1' : null, terminalRunIds: active ? [] : ['user-run-1'], incomplete: false } });
      stream.onEvent({ type: 'run_start', runId: 'user-run-1', trigger: 'user' });
      stream.onEvent({ type: 'delta', runId: 'user-run-1', text: 'Alice works Monday.' });
      stream.onEvent({ type: 'steering', runId: 'user-run-1', messageId: 'queued', message: 'Compare Tuesday.' });
      stream.onEvent({ type: 'delta', runId: 'user-run-1', text: 'Tuesday is free.' });
      stream.onEvent({ type: 'done', runId: 'user-run-1' });
    });
    expect(screen.getAllByText('Alice works Monday.')).toHaveLength(1);
    expect(screen.getByText('Compare Tuesday.')).toBeInTheDocument();
    expect(screen.getByText('Tuesday is free.')).toBeInTheDocument();
    expect(screen.getByText('Alice works Monday.').closest('article')?.nextElementSibling).toHaveTextContent('Compare Tuesday.');
    expect(screen.getByText('Compare Tuesday.').closest('article')?.nextElementSibling).toHaveTextContent('Tuesday is free.');
    expect(screen.getByText('Tuesday is free.').closest('article')?.nextElementSibling).toHaveTextContent('Optimization finished');
  });

  it('keeps a foreground response active when an older background completion is replayed', async () => {
    const user = userEvent.setup();
    let background: SessionStreamOptions | undefined;
    let finishForeground: (() => void) | undefined;
    mockStreamSessionEvents.mockImplementation(async (_id, callbacks) => {
      background = callbacks;
      await new Promise<void>(() => {});
    });
    mockRunEvents.mockImplementation(async () => {
      await new Promise<void>(resolve => { finishForeground = resolve; });
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Keep working');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(finishForeground).toBeDefined());
    act(() => background?.onEvent({ type: 'done', runId: 'previous-turn' }));
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
    await act(async () => finishForeground?.());
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it('sends queued input after a background review finishes', async () => {
    const user = userEvent.setup();
    let background: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (_id, callbacks) => {
      background = callbacks;
      await new Promise<void>(() => {});
    });
    mockQueueMessage.mockRejectedValue(new MockAiHttpError('Not accepting steering', 409));
    render(<ExperimentalAiPage />);
    const input = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    await user.type(input, 'Optimize');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    act(() => background?.onEvent({ type: 'run_start', runId: 'review', trigger: 'optimizer' }));
    await user.type(input, 'Explain the result');
    fireEvent.submit(input.closest('form')!);
    await waitFor(() => expect(mockQueueMessage).toHaveBeenCalledOnce());
    expect(mockRunEvents).toHaveBeenCalledOnce();
    act(() => background?.onEvent({ type: 'done', runId: 'review' }));
    await waitFor(() => expect(mockRunEvents).toHaveBeenCalledTimes(2));
    expect(mockRunEvents.mock.calls[1][1]).toBe('Explain the result');
  });

  it('stops a background assistant turn through the session endpoint', async () => {
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
    act(() => backgroundCallbacks?.onEvent({ type: 'run_start', runId: 'optimizer-turn', trigger: 'optimizer' }));

    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(mockStopSession).toHaveBeenCalledWith('session-id', null, '/ai', undefined);
    act(() => backgroundCallbacks?.onEvent({ type: 'stopped' }));

    expect(screen.getByText('Stopped before completion.')).toBeInTheDocument();
    expect(screen.queryByText('Stopped.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it.each(['done', 'stale', 'error'] as const)(
    'keeps Stop pending until a background turn reports %s',
    async outcome => {
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
      act(() => backgroundCallbacks?.onEvent({ type: 'run_start', runId: 'optimizer-turn', trigger: 'optimizer' }));

      await user.click(screen.getByRole('button', { name: 'Stop' }));
      expect(mockStopSession).toHaveBeenCalledWith('session-id', null, '/ai', undefined);
      // The request is accepted well before the run ends, so the control stays pending.
      await act(async () => {});
      expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();

      act(() => {
        if (outcome === 'done') backgroundCallbacks?.onEvent({ type: 'done', runId: 'optimizer-turn' });
        else if (outcome === 'stale') backgroundCallbacks?.onEvent({ type: 'stale', message: 'This chat became stale.' });
        else backgroundCallbacks?.onEvent({ type: 'error', message: 'The AI response failed.' });
      });

      expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();

      // A run that ended any other way must not leave the next one unable to stop.
      act(() => backgroundCallbacks?.onEvent({ type: 'run_start', runId: 'optimizer-turn-2', trigger: 'optimizer' }));
      expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
    },
  );

  it('shows all steering messages before one assistant response without empty turns', async () => {
    const user = userEvent.setup();
    let callbacks: SessionStreamOptions | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      streamCallbacks: SessionStreamOptions,
    ) => {
      callbacks = streamCallbacks;
      streamCallbacks.onEvent({ type: 'tool_start', activity: { name: 'read', arguments: '{}' } });
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    render(<ExperimentalAiPage />);
    const draft = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });

    await user.type(draft, 'Inspect P1.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(callbacks).toBeDefined());
    const activeSignal = mockRunEvents.mock.calls[0][3] as AbortSignal;
    await user.type(draft, 'Focus on P2 instead.');
    const queueButton = screen.getByRole('button', { name: 'Queue message' });
    expect(queueButton).toHaveTextContent('');
    expect(queueButton.querySelector('svg')).not.toBeNull();
    await user.click(queueButton);
    await user.type(draft, 'Also compare P3.');
    await user.click(queueButton);

    expect(screen.getByText('Queued for steering')).toBeInTheDocument();
    expect(activeSignal.aborted).toBe(false);
    expect(mockQueueMessage).toHaveBeenCalledTimes(2);
    const firstQueuedId = mockQueueMessage.mock.calls[0][1] as string;
    const secondQueuedId = mockQueueMessage.mock.calls[1][1] as string;
    act(() => {
      callbacks?.onEvent({ type: 'steering', messageId: firstQueuedId, message: 'Focus on P2 instead.' });
      callbacks?.onEvent({ type: 'steering', messageId: secondQueuedId, message: 'Also compare P3.' });
    });

    expect(screen.queryByText('Queued for steering')).not.toBeInTheDocument();
    expect(screen.getByText('Steering…')).toBeInTheDocument();
    expect(screen.getByText('Focus on P2 instead.')).toBeInTheDocument();
    expect(screen.getByText('Also compare P3.')).toBeInTheDocument();
    const messageCards = screen.getByLabelText('Chat messages').querySelectorAll('article');
    expect(Array.from(messageCards, card => card.querySelector('p')?.textContent)).toEqual([
      'User',
      'Assistant',
      'User',
      'User',
      'Assistant',
    ]);
    const stopButton = screen.getByRole('button', { name: 'Stop' });
    expect(stopButton).toHaveTextContent('');
    expect(stopButton.querySelector('svg')).not.toBeNull();
    await act(async () => finishStream?.());
  });

  it('keeps alternating response and tool events in stream order', async () => {
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      callbacks.onEvent({ type: 'reasoning', text: 'First thought.' });
      callbacks.onEvent({ type: 'delta', text: 'First response.' });
      callbacks.onEvent({ type: 'delta', text: ' Continued.' });
      callbacks.onEvent({ type: 'tool_start', activity: { name: 'lookup', arguments: '{}' } });
      callbacks.onEvent({ type: 'tool', activity: { name: 'lookup', arguments: '{}', result: 'found', ok: true } });
      callbacks.onEvent({ type: 'delta', text: 'Second response.' });
      callbacks.onEvent({ type: 'tool_start', activity: { name: 'calculate', arguments: '{}' } });
      callbacks.onEvent({ type: 'tool', activity: { name: 'calculate', arguments: '{}', result: '42', ok: true } });
      callbacks.onEvent({ type: 'delta', text: 'Final response.' });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Work in stages.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const activity = await screen.findByLabelText('Assistant activity');
    const ordered = [
      screen.getByText('Reasoning · 14 characters'),
      screen.getByText('First response. Continued.'),
      screen.getByText('lookup'),
      screen.getByText('Second response.'),
      screen.getByText('calculate'),
      screen.getByText('Final response.'),
    ];
    ordered.slice(1).forEach((entry, index) => {
      expect(ordered[index].compareDocumentPosition(entry) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
    expect(activity.querySelectorAll('hr')).toHaveLength(5);
  });

  it('completes each concurrent tool call on the row that shares its ID', async () => {
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      const first = { toolCallId: 'call-a', name: 'read', arguments: '{"path":"a.txt"}' };
      const second = { toolCallId: 'call-b', name: 'read', arguments: '{"path":"b.txt"}' };
      callbacks.onEvent({ type: 'tool_start', activity: first });
      callbacks.onEvent({ type: 'tool_start', activity: second });
      // A parallel batch reports its results in call order after starting every call.
      callbacks.onEvent({ type: 'tool', activity: { ...first, result: 'contents of a', ok: false } });
      callbacks.onEvent({ type: 'tool', activity: { ...second, result: 'contents of b', ok: true } });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Read both.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await screen.findByText('contents of b');
    const [firstRow, secondRow] = (await screen.findByLabelText('Assistant activity')).querySelectorAll('details');
    expect(firstRow).toHaveTextContent('{"path":"a.txt"}');
    expect(firstRow).toHaveTextContent('read · failed');
    expect(firstRow).toHaveTextContent('contents of a');
    expect(secondRow).toHaveTextContent('{"path":"b.txt"}');
    expect(secondRow).toHaveTextContent('contents of b');
    expect(secondRow).not.toHaveTextContent('failed');
  });
  it('keeps replayed completed answers beside their original questions', async () => {
    mockRunEvents.mockImplementation(async (_session: string, question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'delta', text: `Answer to ${question}` });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    for (const question of ['Q1', 'Q2']) {
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), question);
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await screen.findByText(`Answer to ${question}`);
      await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
    }
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => {
      stream.onEvent({ type: 'session_reset', reset: { runIds: ['user-run-1', 'user-run-2'], activeRunId: null, terminalRunIds: ['user-run-1', 'user-run-2'], incomplete: false } });
      for (const [runId, question] of [['user-run-1', 'Q1'], ['user-run-2', 'Q2']]) {
        stream.onEvent({ type: 'run_start', runId, trigger: 'user' });
        stream.onEvent({ type: 'delta', runId, text: `Answer to ${question}` });
        stream.onEvent({ type: 'done', runId });
      }
    });
    act(() => window.dispatchEvent(new Event('pagehide')));
    const saved = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    const order = saved.messages.filter((entry: { role: string; source?: string }) => !entry.source && ['user', 'assistant'].includes(entry.role)).map((entry: { content: string }) => entry.content);
    expect(order).toEqual(['Q1', 'Answer to Q1', 'Q2', 'Answer to Q2']);
  });
  it('applies each replayed model input to the correct run in one reset', async () => {
    mockRunEvents.mockImplementation(async (_session: string, question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'delta', text: `Answer to ${question}` });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    for (const question of ['Q1', 'Q2']) {
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), question);
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await screen.findByText(`Answer to ${question}`);
      await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
    }
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => {
      stream.onEvent({ type: 'session_reset', reset: { runIds: ['user-run-1', 'user-run-2'], activeRunId: null, terminalRunIds: ['user-run-1', 'user-run-2'], incomplete: false } });
      for (const [runId, question] of [['user-run-1', 'Q1'], ['user-run-2', 'Q2']]) {
        stream.onEvent({ type: 'run_context', runId });
        stream.onEvent({ type: 'run_start', runId, trigger: 'user' });
        stream.onEvent({ type: 'model_input', runId, input: { system: `Recovered system ${question}`, messages: [{ kind: 'question', content: `Recovered ${question}` }] } });
        stream.onEvent({ type: 'delta', runId, text: `Recovered answer ${question}` });
        stream.onEvent({ type: 'done', runId });
      }
    });
    act(() => window.dispatchEvent(new Event('pagehide')));
    const saved = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
    const contents = saved.messages.map((entry: { content: string }) => entry.content);
    expect(contents).toContain('Recovered Q1');
    expect(contents).toContain('Recovered Q2');
    expect(contents).toContain('Recovered system Q1');
    expect(contents).toContain('Recovered system Q2');
  });

  it('replaces saved call details when a recovery snapshot replaces the answer', async () => {
    const call = { callId: 'old', model: 'model', reasoning: 'high', status: 'reported' as const,
      costUsd: '0.1', providerCallId: 'old-gateway', responseModel: null, usage: null };
    mockRunEvents.mockImplementation(async (_session: string, _question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'delta', text: 'Costed answer' });
      callbacks.onEvent({ type: 'provider_call', call });
      callbacks.onEvent({ type: 'cost_summary', conversation: { usd: '0.1', calls: 1, pending: 0, unavailable: 0, version: 2 },
        run: { usd: '0.1', calls: 1, pending: 0, unavailable: 0 } });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Cost question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Turn details · ~$0.1000 · Speed unavailable · 1 call');
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => {
      stream.onEvent({ type: 'session_reset', reset: { runIds: ['user-run-1'], activeRunId: null, terminalRunIds: ['user-run-1'], incomplete: false } });
      stream.onEvent({ type: 'run_start', runId: 'user-run-1', trigger: 'user' });
      stream.onEvent({ type: 'delta', runId: 'user-run-1', text: 'Restored answer' });
      stream.onEvent({ type: 'provider_call', runId: 'user-run-1', call: { ...call, callId: 'new', providerCallId: 'new-gateway', costUsd: '0.2' } });
      stream.onEvent({ type: 'cost_summary', runId: 'user-run-1', conversation: { usd: '0.2', calls: 1, pending: 0, unavailable: 0, version: 20 },
        run: { usd: '0.2', calls: 1, pending: 0, unavailable: 0 } });
      stream.onEvent({ type: 'done', runId: 'user-run-1' });
    });
    expect(screen.getByText('Turn details · ~$0.2000 · Speed unavailable · 1 call')).toBeInTheDocument();
    expect(screen.queryByText('Call: old-gateway')).not.toBeInTheDocument();
    expect(screen.getByText('Call: new-gateway')).toBeInTheDocument();
  });
});
