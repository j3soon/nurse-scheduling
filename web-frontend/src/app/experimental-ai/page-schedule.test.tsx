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
  mockRunEvents,
  mockSendMessage,
  mockStreamSessionEvents,
  mockStopSession,
  mockGenerateYaml,
  mockUpdateSessionSchedule,
  mockLoadFromYaml,
  MockAiStaleRunError,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('reports browser edits without sending them during an active response', async () => {
    let finish!: () => void;
    mockRunEvents.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
    const user = userEvent.setup();
    const view = render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Review this schedule');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByRole('button', { name: 'Stop' });
    mockGenerateYaml.mockReturnValue('description: manually edited schedule\n');
    view.rerender(<ExperimentalAiPage />);
    expect(screen.getByLabelText('Schedule Spec status')).toHaveTextContent('This response keeps its Schedule Spec');
    expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
    await act(async () => finish());
    expect(screen.getByLabelText('Schedule Spec status')).toHaveTextContent('Sending your next message');
  });

  it('ignores output and Schedule Spec changes from the previous conversation stream', async () => {
    const user = userEvent.setup();
    let background: SessionStreamOptions | undefined;
    mockStreamSessionEvents.mockImplementation(async (_id, callbacks) => {
      background = callbacks;
      await new Promise<void>(() => {});
    });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Optimize');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('Alice works Monday.');
    await user.click(screen.getByRole('button', { name: 'Start new chat' }));
    act(() => {
      background?.onEvent({ type: 'run_start', runId: 'old', trigger: 'optimizer' });
      background?.onEvent({ type: 'delta', text: 'Leaked old answer' });
      background?.onEvent({ type: 'schedule_spec_applied', applied: {
        runId: 'old', scheduleSpecYaml: 'description: old\n', diff: 'Old change', replacedQueuedScheduleSpec: false,
      } });
      background?.onEventId?.(900);
    });
    expect(screen.queryByText('Leaked old answer')).not.toBeInTheDocument();
    expect(screen.queryByText('Applied to your Schedule Spec')).not.toBeInTheDocument();
    expect(mockLoadFromYaml).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it('removes provisional output when the backend discards a stale turn', async () => {
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      callbacks.onEvent({ type: 'schedule_spec_change', scheduleSpecYaml: 'description: obsolete proposal' });
      callbacks.onEvent({ type: 'delta', text: 'Obsolete response.' });
      throw new MockAiStaleRunError('The Schedule Spec changed.');
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Change it.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('This response failed before completion. Send a new message to continue.')).toBeInTheDocument();
    expect(screen.getByText('The Schedule Spec changed.')).toBeInTheDocument();
    expect(screen.queryByText('Obsolete response.')).not.toBeInTheDocument();
    expect(screen.queryByText('Schedule Spec edit')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  describe('applied Schedule Spec changes', () => {
    const check = 'Trusted Schedule Spec check after this command:\nThe candidate passed trusted server-side validation.';
    const changingStream = (replacedQueuedScheduleSpec = false) => async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      callbacks.onEvent({ type: 'tool', activity: {
        name: 'bash', arguments: '{"command":"edit"}', result: `exit_code: 0\n\n${check}`, ok: true,
        scheduleSpecCheck: { ok: true, text: check },
      } });
      callbacks.onEvent({ type: 'schedule_spec_change', scheduleSpecYaml: 'description: Head\n' });
      callbacks.onEvent({ type: 'delta', text: 'I set the description.' });
      callbacks.onEvent({ type: 'schedule_spec_applied', applied: {
        runId: 'change-run', scheduleSpecYaml: 'description: Head\n',
        diff: '- description: "current Schedule Spec" -> "Head"', replacedQueuedScheduleSpec,
      } });
    };

    const ask = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Set the description.');
      await user.click(screen.getByRole('button', { name: 'Send' }));
    };

    it('applies the schedule a run finished with as one history entry and shows its check', async () => {
      mockRunEvents.mockImplementationOnce(changingStream());
      const user = userEvent.setup();
      render(<ExperimentalAiPage />);
      await ask(user);

      await waitFor(() => expect(mockLoadFromYaml).toHaveBeenCalledTimes(1));
      expect(mockLoadFromYaml).toHaveBeenCalledWith({ description: 'Head' });
      expect(screen.queryByText(/replaced changes made during this response/)).not.toBeInTheDocument();
      expect(screen.getByText('Schedule Spec check passed')).toBeInTheDocument();
      expect(screen.getByText('Applied to your Schedule Spec')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    });

    it('shows a notice when the run replaced a queued browser update without controlling the agent', async () => {
      mockRunEvents.mockImplementationOnce(changingStream(true));
      const user = userEvent.setup();
      render(<ExperimentalAiPage />);
      await ask(user);

      expect(await screen.findByText('Applied to your Schedule Spec')).toBeInTheDocument();
      expect(mockLoadFromYaml).toHaveBeenCalledWith({ description: 'Head' });
      expect(screen.getByText(/replaced changes made during this response/)).toBeVisible();
      expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
      expect(mockStopSession).not.toHaveBeenCalled();
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    it('notices an edit made while the response runs and applies each run only once', async () => {
      let callbacks!: SessionStreamOptions;
      let finish!: () => void;
      mockRunEvents.mockImplementationOnce((_id, _question, stream) => {
        callbacks = stream;
        return new Promise<void>(resolve => { finish = resolve; });
      });
      const user = userEvent.setup();
      const view = render(<ExperimentalAiPage />);
      await ask(user);
      await waitFor(() => expect(callbacks).toBeDefined());
      mockGenerateYaml.mockReturnValue('description: edited during response\n');
      view.rerender(<ExperimentalAiPage />);
      await act(async () => {
        await changingStream()('', '', callbacks);
        finish();
      });
      expect(mockLoadFromYaml).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/replaced changes made during this response/)).toBeVisible();
      // Undo is a browser action. A replacement replay must not overwrite it again.
      mockGenerateYaml.mockReturnValue('description: restored with Undo\n');
      view.rerender(<ExperimentalAiPage />);
      await act(async () => changingStream()('', '', callbacks));
      expect(mockLoadFromYaml).toHaveBeenCalledTimes(1);
      expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
      expect(mockStopSession).not.toHaveBeenCalled();
    });

    it('shows a failed schedule check that the model received', async () => {
      mockRunEvents.mockImplementationOnce(async (_sessionId: string, _message: string, callbacks: SessionStreamOptions) => {
        callbacks.onEvent({ type: 'tool', activity: {
          name: 'bash', arguments: '{"command":"break"}', result: 'Broken.', ok: false,
          scheduleSpecCheck: { ok: false, text: 'schedule.yaml introduces problems and cannot be applied.' },
        } });
      });
      const user = userEvent.setup();
      render(<ExperimentalAiPage />);
      await ask(user);

      await screen.findByText('Schedule Spec check failed');
      expect(screen.getByText('schedule.yaml introduces problems and cannot be applied.')).toBeVisible();
    });

    it('restores application receipts so replay preserves Undo after a reload', async () => {
      window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
        sessionId: 'session-id', endpoint: '/ai', expiresAt: Date.now() + 300000,
        retentionSeconds: 300, messages: [], syncedScheduleSpec: 'description: Head\n',
        syncedBrowserScheduleSpec: 'description: Head\n',
        appliedScheduleSpecRuns: { 'change-run': null },
      }));
      mockGenerateYaml.mockReturnValue('description: restored with Undo\n');
      render(<ExperimentalAiPage />);
      await waitFor(() => expect(mockStreamSessionEvents).toHaveBeenCalled());
      const stream = mockStreamSessionEvents.mock.calls.at(-1)![1] as SessionStreamOptions;
      await act(async () => changingStream()('', '', stream));
      expect(mockLoadFromYaml).not.toHaveBeenCalled();
      expect(mockSendMessage).not.toHaveBeenCalled();
      expect(mockStopSession).not.toHaveBeenCalled();
      expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
    });

    it('sends a changed schedule to an existing session before the next question', async () => {
      const user = userEvent.setup();
      render(<ExperimentalAiPage />);
      await ask(user);
      mockGenerateYaml.mockReturnValue('description: edited elsewhere\n');

      await ask(user);

      await waitFor(() => expect(mockUpdateSessionSchedule).toHaveBeenCalledWith(
        'session-id',
        'description: edited elsewhere\n',
        null,
        '/ai',
      ));
      expect(mockCreateSession).toHaveBeenCalledTimes(1);
    });
  });
});
