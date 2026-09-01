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
import { ActivityEntry, AssistantActivity } from './AssistantActivity';

const bashEntry: ActivityEntry = {
  kind: 'tool',
  name: 'bash',
  arguments: JSON.stringify({ command: "sed -i 's/old/new/' schedule.yaml" }),
  result: 'exit_code: 0',
  ok: true,
};

describe('AssistantActivity', () => {
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

  it('shows Bash arguments and output', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[bashEntry]} />);

    await user.click(screen.getByText('bash'));

    expect(screen.getByText(/sed -i/)).toBeVisible();
    expect(screen.getByText('exit_code: 0')).toBeVisible();
  });

  it('reveals long output one chunk at a time', async () => {
    const user = userEvent.setup();
    const longResult = 'x'.repeat(2500);
    render(<AssistantActivity entries={[{ kind: 'tool', name: 'bash', arguments: '{}', result: longResult, ok: true }]} />);

    await user.click(screen.getByText('bash'));

    const more = screen.getByRole('button', { name: 'Show more output (500 characters left)' });
    await user.click(more);
    expect(screen.queryByRole('button', { name: /Show more output/ })).not.toBeInTheDocument();
  });

  it('keeps entries in the order the assistant produced them', () => {
    render(
      <AssistantActivity
        entries={[
          { kind: 'reasoning', text: 'First thought.' },
          { kind: 'tool', name: 'bash', arguments: '{}', result: 'lines', ok: true },
          { kind: 'reasoning', text: 'Second thought.' },
        ]}
      />,
    );

    const summaries = screen.getAllByText(/Reasoning ·|bash/).map(element => element.textContent);
    expect(summaries).toEqual(['Reasoning · 14 characters', 'bash', 'Reasoning · 15 characters']);
  });
});
