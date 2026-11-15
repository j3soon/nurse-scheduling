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
  mockCompactSession,
  mockRunEvents,
  mockStreamSessionEvents,
  mockStopSession,
  mockQueueMessage,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('explains when the server does not report context usage', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    const usage = await screen.findByText('Context unavailable');
    expect(usage).toHaveAttribute('title', expect.stringContaining('The AI server has not reported context tokens.'));
    expect(usage.closest('form')).toBeInTheDocument();
  });

  it('does not use the character budget as a model context percentage', async () => {
    const user = userEvent.setup();
    mockRunEvents.mockImplementationOnce(async (_id, _message, callbacks) => {
      callbacks.onEvent({ type: 'context_usage', usage: { usedChars: 500, maxChars: 2000 } });
      callbacks.onEvent({ type: 'delta', text: 'Done.' });
    });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ExperimentalAiPage />);
    expect(screen.queryByText(/Context /)).not.toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    const usage = await screen.findByText('Context unavailable');
    expect(usage).toHaveAttribute('title', expect.stringContaining('not reported context tokens'));
    expect(usage.closest('form')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Start new chat' }));
    expect(screen.queryByText(/Context /)).not.toBeInTheDocument();
  });

  it.each([131072, undefined])('uses the same context tokens for percentage and count with limit %s', async maxTokens => {
    const user = userEvent.setup();
    mockRunEvents.mockImplementationOnce(async (_id: string, _message: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'context_usage', usage: { usedChars: 500, maxChars: 2000, usedTokens: 4321, maxTokens, estimated: true } });
      // A report without tokens, such as the next run's first one, keeps the latest token figures.
      callbacks.onEvent({ type: 'context_usage', usage: { usedChars: 600, maxChars: 2000 } });
      callbacks.onEvent({ type: 'delta', text: 'Done.' });
    });
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const usage = await screen.findByText(maxTokens ? 'Context ~3.3% used' : 'Context unavailable');
    expect(usage).toHaveAttribute('title', expect.stringContaining('current LLM context'));
    const tokens = screen.getByText(`Tokens: ~4,321 / ${maxTokens ? '131,072' : 'unavailable'}`);
    expect(tokens).toHaveAttribute('title', 'Estimated current LLM context tokens / model context limit. Includes system instructions, tools, and conversation messages.');
  });

  it('compacts an idle conversation through the session stream without sending a question', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works Monday?');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    await user.click(screen.getByRole('button', { name: 'Compact context' }));
    expect(mockCompactSession).toHaveBeenCalledWith('session-id', expect.any(String), null, '/ai', {
      signal: expect.any(AbortSignal), shouldStop: expect.any(Function), onConnectionChange: expect.any(Function),
    });
    expect(mockRunEvents).toHaveBeenCalledTimes(1);
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    await act(async () => {
      stream.onEvent!({ type: 'run_start', runId: 'compact-run', trigger: 'compaction' });
      stream.onEvent!({ type: 'compaction_start', runId: 'compact-run', reason: 'manual', tokensBefore: 12000 });
    });
    expect(screen.getByRole('button', { name: 'Compact context' })).toBeDisabled();
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
    expect(composer).toBeEnabled();
    await user.type(composer, 'Draft during compaction');
    expect(screen.getByRole('button', { name: 'Queue message' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }));
    expect(mockQueueMessage).not.toHaveBeenCalled();
    expect(composer).toHaveValue('Draft during compaction');
    expect(screen.getByText('You requested context compaction.')).toBeVisible();
    await act(async () => {
      stream.onEvent!({ type: 'compaction_end', runId: 'compact-run', reason: 'manual', tokensBefore: 12000,
        success: true, aborted: false, summary: 'Keep the night constraints.', keepMessages: 2, estimatedTokensAfter: 1000 });
      stream.onEvent!({ type: 'context_usage', runId: 'compact-run', usage: { usedChars: 1000, maxChars: 200000,
        usedTokens: 1000, maxTokens: 10000, estimated: true } });
      stream.onEvent!({ type: 'done', runId: 'compact-run' });
    });
    expect(screen.getByRole('button', { name: 'Compact context' })).toBeEnabled();
    expect(composer).toHaveValue('Draft during compaction');
    expect(screen.getByText('Context ~10.0% used')).toBeInTheDocument();
    expect(screen.getByText('Tokens: ~1,000 / 10,000')).toBeInTheDocument();
    await user.click(screen.getByText('Conversation summary', { exact: true }));
    expect(screen.getByText(/\[Conversation summary\]\s+Keep the night constraints\./)).toBeInTheDocument();
  });

  it.each([true, false])('can stop compaction before run_start, with terminal before acceptance=%s', async terminalBeforeAcceptance => {
    const user = userEvent.setup();
    let accept: ((id: string) => void) | undefined;
    mockCompactSession.mockImplementationOnce(() => new Promise<string>(resolve => { accept = resolve; }));
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    await user.click(screen.getByRole('button', { name: 'Compact context' }));
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    const requestId = mockCompactSession.mock.calls[0][1] as string;
    expect(mockStopSession).toHaveBeenLastCalledWith('session-id', null, '/ai', requestId);
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    if (terminalBeforeAcceptance) act(() => stream.onEvent({ type: 'stopped', runId: 'compact-run' }));
    await act(async () => accept?.('compact-run'));
    if (!terminalBeforeAcceptance) {
      await waitFor(() => expect(mockStopSession).toHaveBeenCalledTimes(2));
      expect(mockStopSession).toHaveBeenLastCalledWith('session-id', null, '/ai', requestId);
      act(() => stream.onEvent({ type: 'stopped', runId: 'compact-run' }));
    }
    expect(await screen.findByText('Stopped before completion.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
  });

  it('keeps compaction busy when an unrelated optimizer review finishes', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    await user.click(screen.getByRole('button', { name: 'Compact context' }));
    const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
    act(() => {
      stream.onEvent({ type: 'delta', runId: 'earlier-review', text: 'Earlier review.' });
      stream.onEvent({ type: 'done', runId: 'earlier-review' });
    });
    expect(screen.getByRole('button', { name: 'Stop' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Compact context' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
    await act(async () => stream.onEvent({ type: 'done', runId: 'compact-run' }));
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
  });

  it('releases a rejected compaction and leaves the conversation available', async () => {
    const user = userEvent.setup();
    mockCompactSession.mockRejectedValueOnce(new Error('Compaction is unavailable.'));
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    await user.click(screen.getByRole('button', { name: 'Compact context' }));
    expect(await screen.findByText('Compaction is unavailable.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Compact context' })).toBeEnabled();
  });

  it('warns once the assistant stops receiving the oldest messages', async () => {
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
    expect(screen.queryByText(/no longer sent to the assistant/)).not.toBeInTheDocument();

    act(() => backgroundCallbacks?.onEvent({ type: 'history_trimmed', dropped: 4 }));

    expect(screen.getByText(/4 oldest messages are/)).toBeInTheDocument();
    expect(screen.getByText(/no longer sent to the assistant/)).toBeInTheDocument();
  });

  it('keeps the trim warning across a reload and drops it with a new chat', async () => {
    const user = userEvent.setup();
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session',
      endpoint: '/ai',
      expiresAt: Date.now() + 60_000,
      retentionSeconds: 172800,
      messages: [{ id: 'answer-1', role: 'assistant', content: 'Earlier answer.' }],
      syncedScheduleSpec: 'description: current Schedule Spec\n',
      sessionEventId: 9,
      trimmedHistoryCount: 3,
    }));

    render(<ExperimentalAiPage />);

    // The event announcing the trim is behind the stored cursor, so it never replays.
    expect(await screen.findByText(/3 oldest messages are/)).toBeInTheDocument();

    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Start new chat' }));

    expect(screen.queryByText(/no longer sent to the assistant/)).not.toBeInTheDocument();
  });

  it('drops the trim warning when the restored conversation has expired', async () => {
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session',
      endpoint: '/ai',
      expiresAt: Date.now() - 1_000,
      retentionSeconds: 172800,
      messages: [{ id: 'answer-1', role: 'assistant', content: 'Earlier answer.' }],
      syncedScheduleSpec: 'description: current Schedule Spec\n',
      sessionEventId: 9,
      trimmedHistoryCount: 3,
    }));

    render(<ExperimentalAiPage />);

    expect(await screen.findByText(/This chat expired after 2 days of inactivity/)).toBeInTheDocument();
    // An expired chat sends nothing, so a warning about what it omits would mislead.
    expect(screen.queryByText(/no longer sent to the assistant/)).not.toBeInTheDocument();
  });
});
