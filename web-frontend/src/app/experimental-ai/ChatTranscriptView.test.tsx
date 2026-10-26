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
import userEvent from '@testing-library/user-event';

import { ChatTranscriptView } from './ChatTranscriptView';
import { failResponse, staleResponse } from './assistantEvents';
import type { ChatMessage } from './chatTranscript';
import type { ActivityEntry } from './AssistantActivity';

function renderTranscript(messages: ChatMessage[], showTools = false) {
  render(<ChatTranscriptView
    messages={messages}
    showReasoning={false}
    showTools={showTools}
    showCosts={true}
    showModels={true}
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

it('counts Unicode characters in collapsed model inputs', () => {
  renderTranscript([{ id: 'system', role: 'system', content: '新😀' }]);
  expect(screen.getByText('2 characters')).toBeVisible();
});

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
  expect(screen.queryByText('Sent to AI.')).not.toBeInTheDocument();
  expect(screen.getByText('Not sent to AI.')).toBeVisible();
});

it('marks messages before the retained compaction tail as compacted out of context', () => {
  renderTranscript([
    { id: 'system', role: 'system', content: 'Instructions' },
    { id: 'q1', role: 'user', content: 'First question' },
    { id: 'a1', role: 'assistant', content: 'First answer', activity: [
      { kind: 'tool', name: 'read', arguments: '{}', result: 'Read output', ok: true },
      { kind: 'response', text: 'First answer' },
    ] },
    { id: 'q2', role: 'user', content: 'Second question' },
    { id: 'a2', role: 'assistant', content: 'Second answer', activity: [
      { kind: 'response', text: 'Second answer' },
    ] },
    { id: 'compact', role: 'assistant', content: '', activity: [
      { kind: 'notice', text: 'You requested context compaction.' },
      { kind: 'compaction', reason: 'manual', state: 'completed', text: 'The conversation was summarized.',
        summary: 'Summary text.', keepMessages: 2 },
    ] },
  ]);
  expect(screen.getByText('First question').closest('article')).toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('First answer').closest('article')).toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Second question').closest('article')).not.toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Second answer').closest('article')).not.toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('System').closest('article')).not.toHaveTextContent('Compacted out of context.');
});

it('keeps the newest messages in order across summaries and replaces the earlier summary', () => {
  const answer = (id: string, text: string) => (
    { id, role: 'assistant' as const, content: text, activity: [{ kind: 'response' as const, text }] });
  const compaction = (id: string, keepMessages: number) => ({ id, role: 'assistant' as const, content: '', activity: [
    { kind: 'compaction' as const, reason: 'manual' as const, state: 'completed' as const,
      text: 'The conversation was summarized.', summary: `Summary ${id}.`, keepMessages },
  ] });
  renderTranscript([
    { id: 'q1', role: 'user', content: 'First question' }, answer('a1', 'First answer'),
    { id: 'q2', role: 'user', content: 'Second question' }, answer('a2', 'Second answer'),
    compaction('first', 2),
    { id: 'q3', role: 'user', content: 'Third question' }, answer('a3', 'Third answer'),
    { id: 'q4', role: 'user', content: 'Fourth question' }, answer('a4', 'Fourth answer'),
    // The earlier summary is folded into the new one, so only conversation messages count.
    compaction('second', 5),
  ]);
  const status = (text: string) => screen.getByText(text).closest('article');
  for (const text of ['First question', 'First answer', 'Second question']) {
    expect(status(text)).toHaveTextContent('Compacted out of context.');
  }
  for (const text of ['Second answer', 'Third question', 'Third answer', 'Fourth question', 'Fourth answer']) {
    expect(status(text)).not.toHaveTextContent('Compacted out of context.');
  }
  const summaries = screen.getAllByText('User · Conversation summary').map(label => label.closest('article'));
  expect(summaries[0]).toHaveTextContent('Compacted out of context.');
  expect(summaries[1]).not.toHaveTextContent('Compacted out of context.');
});

it('counts parallel tool calls as one step and ignores uncommitted turns when marking compacted messages', () => {
  renderTranscript([
    { id: 'q1', role: 'user', content: 'Compacted question' },
    { id: 'a1', role: 'assistant', content: 'Compacted answer', activity: [
      { kind: 'response', text: 'Compacted answer' },
    ] },
    { id: 'q2', role: 'user', content: 'Retained question' },
    { id: 'a2', role: 'assistant', content: 'Retained answer', activity: [
      { kind: 'reasoning', text: 'Checking both files.' },
      { kind: 'tool', name: 'read', arguments: '{"path":"a"}', result: 'A', ok: true },
      { kind: 'tool', name: 'read', arguments: '{"path":"b"}', result: 'B', ok: true },
      { kind: 'response', text: 'Retained answer' },
    ] },
    { id: 'q-stale', role: 'user', content: 'Stale question' },
    staleResponse({ id: 'a-stale', role: 'assistant', content: '' }, 'This response was not saved.'),
    { id: 'q-unsent', role: 'user', content: 'Unsent question' },
    failResponse({ id: 'a-unsent', role: 'assistant', content: '', unsentFiles: ['ward.xlsx'] }, 'Upload failed.'),
    { id: 'compact', role: 'assistant', content: '', activity: [
      { kind: 'notice', text: 'You requested context compaction.' },
      { kind: 'compaction', reason: 'manual', state: 'completed', text: 'The conversation was summarized.',
        summary: 'Summary text.', keepMessages: 5 },
    ] },
  ]);
  expect(screen.getByText('Compacted question').closest('article')).toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Compacted answer').closest('article')).toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Retained question').closest('article')).not.toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Retained answer').closest('article')).not.toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Stale question').closest('article')).not.toHaveTextContent('Compacted out of context.');
  expect(screen.getByText('Unsent question').closest('article')).not.toHaveTextContent('Compacted out of context.');
});

it.each([0, 4])('separates compaction notices, summary, and assistant activity with %s retained messages', async keepMessages => {
  const user = userEvent.setup();
  const message: ChatMessage = { id: 'answer', role: 'assistant', content: 'Continued.', activity: [
    { kind: 'tool', name: 'read', arguments: '{}', result: 'Tool output', ok: true },
    { kind: 'notice', text: 'You requested context compaction.' },
    { kind: 'compaction', reason: 'manual', state: 'completed', text: 'The conversation was summarized.',
      summary: 'Keep nights.', keepMessages },
    { kind: 'response', text: 'Continued.' },
    { kind: 'schedule-applied', text: 'Updated the schedule.' },
  ] };
  const saved = structuredClone(message);
  renderTranscript([message], true);
  expect(screen.getByText('read').closest('article')).toHaveClass('mr-auto');
  expect(screen.getByText('You requested context compaction.').closest('article')).toHaveClass('mx-auto');
  expect(screen.getByText('Conversation summarized').closest('article')).toHaveClass('mx-auto');
  expect(screen.getByText('User · Conversation summary').closest('article')).toHaveClass('ml-auto');
  expect(screen.getByText('Continued.').closest('article')).toHaveClass('mr-auto');
  expect(screen.getByText('Applied to your schedule').closest('article')).toHaveClass('mx-auto');
  await user.click(screen.getByText('read'));
  expect(screen.getByText('Tool output').closest('article')).toHaveClass('mr-auto');
  await user.click(screen.getByText('Conversation summary', { exact: true }));
  expect(screen.getByText(/\[Conversation summary\]\s+Keep nights\./)).toBeVisible();
  expect(screen.getByText(keepMessages ? 'The latest 4 messages remain unchanged after the summary.'
    : 'The summary replaces all earlier conversation messages in model context.')).toBeVisible();
  expect(message).toEqual(saved);
});

it.each([undefined, 'failed', 'stopped'] as const)('keeps footer details on the answer before a trailing notice with status %s', status => {
  renderTranscript([{
    id: 'answer', role: 'assistant', content: 'Updated.', status, failureReason: 'The provider failed.',
    createdAt: 1000, responseStartedAt: 1000, responseCompletedAt: 2500,
    modelSelection: { model: 'test-model', reasoning: 'high' },
    costSummary: { usd: '0.02', calls: 1, pending: 0, unavailable: 0 },
    downloadId: 'download-one',
    activity: [
      { kind: 'response', text: 'Updated.' },
      { kind: 'schedule-applied', text: 'The schedule was applied.' },
    ],
  }]);
  const answer = screen.getByText('Updated.').closest('article');
  expect(screen.getByText('test-model · high').closest('article')).toBe(answer);
  expect(screen.getByText(/^Estimated turn cost:/).closest('article')).toBe(answer);
  expect(screen.getByRole('button', { name: 'Download files (ZIP)' }).closest('article')).toBe(answer);
  expect(screen.getByText(/1\.5s/).closest('article')).toBe(answer);
  if (status) expect(screen.getByText(status === 'failed' ? 'The provider failed.' : 'Stopped before completion.')
    .closest('article')).toBe(answer);
});

it('keeps manual compaction metadata on the notice before its summary', () => {
  const message: ChatMessage = {
    id: 'compact', role: 'assistant', content: '',
    createdAt: 1000, responseStartedAt: 1000, responseCompletedAt: 2500,
    modelSelection: { model: 'test-model', reasoning: 'high' },
    costSummary: { usd: '0.02', calls: 1, pending: 0, unavailable: 0 },
    activity: [
      { kind: 'notice', text: 'You requested context compaction.' },
      { kind: 'compaction', reason: 'manual', state: 'completed', text: 'The conversation was summarized.',
        summary: 'Keep nights.', keepMessages: 2 },
    ],
  };
  const saved = structuredClone(message);
  renderTranscript([message]);
  const notice = screen.getByText('Conversation summarized').closest('article');
  expect(screen.getByText('test-model · high').closest('article')).toBe(notice);
  expect(screen.getByText(/^Estimated turn cost:/).closest('article')).toBe(notice);
  expect(screen.getByText(/1\.5s/).closest('article')).toBe(notice);
  expect(screen.getByText('User · Conversation summary').closest('article')).not.toBe(notice);
  expect(message).toEqual(saved);
});

it('keeps failed-summary details and context notices separate from the assistant', () => {
  renderTranscript([{ id: 'answer', role: 'assistant', content: 'Partial.', status: 'failed', failureReason: 'Failed.', activity: [
    { kind: 'compaction', reason: 'threshold', state: 'completed', text: 'Summarized.', summary: 'Old summary.', invalidated: true },
    { kind: 'response', text: 'Partial.' },
    { kind: 'notice', text: 'Sent in future model context: [App event] Workspace discarded.' },
  ] }]);
  expect(screen.getByText('Discarded conversation summary').closest('article')).toHaveClass('mx-auto');
  expect(screen.getByText('Partial.').closest('article')).toHaveClass('mr-auto');
  expect(screen.getByText('Failed.').closest('article')).toHaveClass('mr-auto');
  expect(screen.getByText('[App event] Workspace discarded.').closest('article')).toHaveClass('ml-auto');
});

it('keeps a failed turn without model text on the assistant bubble before its context notice', () => {
  const failed = failResponse({
    id: 'answer',
    role: 'assistant',
    content: '',
    activity: [
      { kind: 'compaction', reason: 'threshold', state: 'completed', text: 'Summarized.', summary: 'Old summary.', invalidated: true },
      { kind: 'notice', text: 'Sent in future model context: [App event] Workspace discarded.' },
    ],
  }, reason);
  renderTranscript([failed]);
  expect(screen.getAllByText(reason)).toHaveLength(1);
  expect(screen.getByText(reason).closest('article')).toHaveClass('mr-auto');
  expect(screen.queryByText(`${reason.length} characters`)).not.toBeInTheDocument();
  expect(screen.getByText('[App event] Workspace discarded.').closest('article')).toHaveClass('ml-auto');
});

it('renders an in-progress manual compaction without an empty assistant bubble', () => {
  renderTranscript([{ id: 'compact', role: 'assistant', content: '', status: 'pending', activity: [
    { kind: 'notice', text: 'You requested context compaction.' },
    { kind: 'compaction', reason: 'manual', state: 'running', text: 'The conversation is being summarized.' },
  ] }]);
  expect(screen.getByText('Summarizing conversation').closest('article')).toHaveClass('mx-auto');
  expect(screen.queryByText('Assistant', { exact: true })).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Thinking')).not.toBeInTheDocument();
});
