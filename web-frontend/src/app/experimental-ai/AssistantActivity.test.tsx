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

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ActivityEntry, AssistantActivity } from './AssistantActivity';

const bashEntry: ActivityEntry = {
  kind: 'tool',
  name: 'bash',
  arguments: JSON.stringify({ command: "sed -i 's/old/new/' schedule.yaml" }),
  result: 'exit_code: 0',
  ok: true,
};

const scheduleChangeEntry: ActivityEntry = {
  kind: 'schedule-change',
  before: "people:\n  - id: P1\n    description: ''\npreferences: []",
  after: 'people:\n  - id: P1\n    description: Head\npreferences: []',
};

describe('AssistantActivity', () => {
  it('shows exact Unicode character counts for responses, reasoning, tools, and compaction', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[
      { kind: 'response', text: '新😀' },
      { kind: 'reasoning', text: '😀'.repeat(1200) },
      { kind: 'compaction', reason: 'manual', state: 'running', text: 'Summarizing', characters: 320, step: 2 },
      { kind: 'tool', name: 'Tool calls', state: 'preparing', argumentsCharacters: 54, arguments: '', result: '', ok: true },
      { ...bashEntry, arguments: '{"x":"新😀"}', result: '新😀' },
    ]} />);
    expect(screen.getAllByText('2 characters')[0]).toBeVisible();
    expect(screen.getByText('Reasoning · 1,200 characters')).toBeVisible();
    expect(screen.getByText('Summarizing conversation · pass 2 · 320 characters')).toBeVisible();
    expect(screen.getByText('Preparing tool calls · 54 characters')).toBeVisible();
    await user.click(screen.getByText('bash'));
    expect(within(screen.getByLabelText('Tool arguments')).getByRole('heading', { name: 'Command · 10 characters' })).toBeVisible();
    expect(within(screen.getByLabelText('Tool result')).getByRole('heading', { name: 'Result · 2 characters' })).toBeVisible();
    expect(screen.getByText('Reasoning · 1,200 characters')).not.toHaveClass('select-none');
    expect(screen.getByText('Summarizing conversation · pass 2 · 320 characters')).not.toHaveClass('select-none');
  });
  it('shows the exact user-role compaction summary and tool replay arguments', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[
      { kind: 'compaction', state: 'completed', reason: 'threshold', text: 'The conversation was summarized.',
        summary: 'Keep P1 off nights.', keepMessages: 4 },
      { ...bashEntry, result: 'Not executed because the response was truncated.', ok: false, replayArguments: '{}' },
    ]} />);
    await user.click(screen.getByText('Conversation summarized'));
    expect(screen.getByText(/\[Conversation summary\]\s+Keep P1 off nights\./)).toBeVisible();
    expect(screen.getByText('The latest 4 messages remain unchanged after the summary.')).toBeVisible();
    await user.click(screen.getByText('bash · failed'));
    expect(screen.getByLabelText('Arguments sent in model context')).toHaveTextContent('{}');
  });
  it('renders nothing when there is no activity', () => {
    const { container } = render(<AssistantActivity entries={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('keeps every entry collapsed until it is opened', () => {
    render(<AssistantActivity entries={[{ kind: 'reasoning', text: 'Counting the people on nights.' }]} />);

    expect(screen.getByText('Reasoning · 30 characters')).toBeInTheDocument();
    expect(screen.getByText('Counting the people on nights.')).not.toBeVisible();
  });

  it('reveals reasoning when its summary is clicked', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[{ kind: 'reasoning', text: 'Counting the people on nights.' }]} />);

    await user.click(screen.getByText('Reasoning · 30 characters'));

    expect(screen.getByText('Counting the people on nights.')).toBeVisible();
  });

  it('marks a failed tool call without opening it', () => {
    render(<AssistantActivity entries={[{ ...bashEntry, ok: false, result: 'exit_code: 1' }]} />);

    expect(screen.getByText('bash · failed')).toBeInTheDocument();
    expect(screen.getByText('exit_code: 1')).not.toBeVisible();
  });

  it('distinguishes running and interrupted tool calls', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<AssistantActivity entries={[{ ...bashEntry, state: 'running', result: '' }]} />);

    expect(screen.getByText('bash · running')).toBeInTheDocument();
    rerender(<AssistantActivity entries={[{ ...bashEntry, state: 'interrupted', result: '' }]} />);
    await user.click(screen.getByText('bash · interrupted'));

    expect(screen.getByText('The command did not return before the turn ended.')).toBeVisible();
  });

  it('shows Bash arguments and output', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[bashEntry]} />);

    await user.click(screen.getByText('bash'));

    const argumentsSection = screen.getByRole('region', { name: 'Tool arguments' });
    const resultSection = screen.getByRole('region', { name: 'Tool result' });
    expect(within(argumentsSection).getByRole('heading', { name: /^Command · / })).toBeVisible();
    expect(within(argumentsSection).getByText(/sed -i/)).toBeVisible();
    expect(within(resultSection).getByRole('heading', { name: /^Result · / })).toBeVisible();
    expect(within(resultSection).getByText('exit_code: 0')).toBeVisible();
    expect(within(argumentsSection).queryByText('exit_code: 0')).not.toBeInTheDocument();
  });

  it('labels non-shell input as arguments and omits an empty result', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[{ kind: 'tool', name: 'read', arguments: '{"path":"/workspace/schedule.yaml"}', result: '', ok: true, state: 'running' }]} />);
    await user.click(screen.getByText('read · running'));
    expect(screen.getByRole('heading', { name: /^Arguments · / })).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Tool result' })).not.toBeInTheDocument();
  });

  it('shows a simple red and green schedule edit', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[scheduleChangeEntry]} />);

    expect(screen.getByText('schedule edit')).toBeVisible();
    expect(screen.getByText(/description: ''/)).not.toBeVisible();

    await user.click(screen.getByText('schedule edit'));

    expect(screen.getByText(/description: ''/)).toHaveClass('removed');
    expect(screen.getByText(/description: Head/)).toHaveClass('added');
  });

  it.each(['x'.repeat(2500), '😀'.repeat(2001)])('reveals long output in complete Unicode characters', async longResult => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[{ kind: 'tool', name: 'bash', arguments: '{}', result: longResult, ok: true }]} />);

    await user.click(screen.getByText('bash'));

    const remaining = Array.from(longResult).length - 2000;
    const more = screen.getByRole('button', { name: `Show more output (${remaining} characters left)` });
    await user.click(more);
    expect(more.closest('details')).toHaveAttribute('open');
    expect(screen.getByText(Array.from(longResult).slice(2000).join(''))).toBeVisible();
  });

  it('keeps entries in the order the assistant produced them', () => {
    render(
      <AssistantActivity
        entries={[
          { kind: 'reasoning', text: 'First thought.' },
          { kind: 'tool', name: 'bash', arguments: '{}', result: 'lines', ok: true },
          { kind: 'schedule-change', before: 'old', after: 'new' },
          { kind: 'reasoning', text: 'Second thought.' },
        ]}
      />,
    );

    const summaries = screen.getAllByText(/Reasoning ·|bash|schedule edit/).map(element => element.textContent);
    expect(summaries).toEqual([
      'Reasoning · 14 characters',
      'bash',
      'schedule edit',
      'Reasoning · 15 characters',
    ]);
  });

  it('separates alternating reasoning, responses, and tools', () => {
    render(
      <AssistantActivity
        entries={[
          { kind: 'reasoning', text: 'First thought.' },
          { kind: 'response', text: 'First response.' },
          bashEntry,
          { kind: 'response', text: 'Second response.' },
        ]}
      />,
    );

    const activity = screen.getByLabelText('Assistant activity');
    const ordered = [
      screen.getByText('Reasoning · 14 characters'),
      screen.getByText('First response.'),
      screen.getByText('bash'),
      screen.getByText('Second response.'),
    ];
    ordered.slice(1).forEach((entry, index) => {
      expect(ordered[index].compareDocumentPosition(entry) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
    expect(activity.querySelectorAll('hr')).toHaveLength(3);
  });

  it('does not separate adjacent non-response activity', () => {
    render(
      <AssistantActivity
        entries={[
          { ...bashEntry, name: 'first tool' },
          { kind: 'reasoning', text: 'Checking the result.' },
          { ...bashEntry, name: 'second tool' },
          { kind: 'response', text: 'Finished.' },
        ]}
      />,
    );

    expect(screen.getByLabelText('Assistant activity').querySelectorAll('hr')).toHaveLength(1);
  });
});
