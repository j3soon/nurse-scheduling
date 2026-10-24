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

import { render, screen } from '@testing-library/react';

import { ChatTranscriptView } from './ChatTranscriptView';
import { failResponse } from './assistantEvents';
import type { ChatMessage } from './chatTranscript';
import type { ActivityEntry } from './AssistantActivity';

function renderTranscript(messages: ChatMessage[]) {
  render(<ChatTranscriptView
    messages={messages}
    showReasoning={false}
    showTools={false}
    steeringAssistantId={null}
    conversationUnavailable={false}
    removingDownloadId={null}
    downloadingOptimizationId={null}
    downloadGeneratedFiles={vi.fn()}
    removeGeneratedFiles={vi.fn()}
    downloadOptimizationResult={vi.fn()}
    activeSessionId={null}
    sessionExpiresAt={null}
    sessionRetentionSeconds={172800}
  />);
}

const reason = 'The AI provider failed (HTTP 525). Error ID: provider-123.';

it.each<{ label: string; content: string; activity: ActivityEntry[] }>([
  { label: 'no output', content: '', activity: [] },
  { label: 'hidden reasoning', content: '', activity: [{ kind: 'reasoning', text: 'Inspecting the result.' }] },
  { label: 'hidden tools', content: '', activity: [{ kind: 'tool', name: 'read', arguments: '{}', result: 'Ready.', ok: true }] },
  { label: 'partial answer', content: 'Partial answer.', activity: [{ kind: 'response', text: 'Partial answer.' }] },
  { label: 'reason already rendered', content: reason, activity: [{ kind: 'response', text: reason }] },
])('keeps the failure reason visible once with $label', ({ content, activity }) => {
  const message = failResponse({ id: 'answer', role: 'assistant' as const, content, activity }, reason);
  renderTranscript([message]);

  expect(screen.getAllByText(reason)).toHaveLength(1);
  if (content === 'Partial answer.') expect(screen.getByText(content)).toBeVisible();
});

it('shows a rejected schedule check even when tools are hidden', () => {
  renderTranscript([{
    id: 'answer', role: 'assistant', content: '', activity: [
      { kind: 'tool', name: 'write', arguments: '{}', result: 'Private tool details', ok: false },
      { kind: 'schedule-check', ok: false, text: 'Date group ALL is generated automatically. Remove its explicit definition.' },
    ],
  }]);
  expect(screen.queryByText('Private tool details')).not.toBeInTheDocument();
  expect(screen.getByText('Validation result sent to AI.')).toBeVisible();
  expect(screen.getByText('Date group ALL is generated automatically. Remove its explicit definition.')).toBeVisible();
});

it('distinguishes model input from app notices with alignment and labels', () => {
  renderTranscript([
    { id: 'system', role: 'system', content: 'Instructions' },
    { id: 'input', role: 'user', source: 'optimizer', content: 'Result given to AI' },
    { id: 'notice', role: 'optimizer', content: 'Optimization finished.' },
    { id: 'answer', role: 'assistant', content: 'Checking.', activity: [{ kind: 'response', text: 'Checking.' }] },
  ]);
  expect(screen.getByText('System').closest('article')).toHaveClass('ml-auto');
  expect(screen.getByText('User · Optimizer').closest('article')).toHaveClass('ml-auto');
  expect(screen.getByText('Optimizer').closest('article')).toHaveClass('mx-auto');
  expect(screen.getByText('Assistant').closest('article')).toHaveClass('mr-auto');
  expect(screen.getAllByText('Sent to AI.')).toHaveLength(2);
  expect(screen.getByText('App notice. Not sent to AI.')).toBeVisible();
});
