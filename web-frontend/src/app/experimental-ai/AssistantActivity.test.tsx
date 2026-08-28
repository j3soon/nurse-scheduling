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

const editEntry: ActivityEntry = {
  kind: 'tool',
  name: 'edit_schedule',
  arguments: JSON.stringify({ old_str: "description: ''", new_str: 'description: Head nurse' }),
  result: 'schedule.yaml is valid.',
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
    render(<AssistantActivity entries={[{ ...editEntry, ok: false, result: '`old_str` was not found.' }]} />);

    expect(screen.getByText('edit_schedule · failed')).toBeInTheDocument();
    expect(screen.getByText('`old_str` was not found.')).not.toBeVisible();
  });

  it('shows an edit as a before and after diff', async () => {
    const user = userEvent.setup();
    render(<AssistantActivity entries={[editEntry]} />);

    await user.click(screen.getByText('edit_schedule'));

    expect(screen.getByText("- description: ''")).toBeVisible();
    expect(screen.getByText('+ description: Head nurse')).toBeVisible();
    expect(screen.getByText('schedule.yaml is valid.')).toBeVisible();
  });

  it('reveals long output one chunk at a time', async () => {
    const user = userEvent.setup();
    const longResult = 'x'.repeat(2500);
    render(<AssistantActivity entries={[{ kind: 'tool', name: 'view_schedule', arguments: '{}', result: longResult, ok: true }]} />);

    await user.click(screen.getByText('view_schedule'));

    const more = screen.getByRole('button', { name: 'Show more output (500 characters left)' });
    await user.click(more);
    expect(screen.queryByRole('button', { name: /Show more output/ })).not.toBeInTheDocument();
  });

  it('keeps entries in the order the assistant produced them', () => {
    render(
      <AssistantActivity
        entries={[
          { kind: 'reasoning', text: 'First thought.' },
          { kind: 'tool', name: 'view_schedule', arguments: '{}', result: 'lines', ok: true },
          { kind: 'reasoning', text: 'Second thought.' },
        ]}
      />,
    );

    const summaries = screen.getAllByText(/Reasoning ·|view_schedule/).map(element => element.textContent);
    expect(summaries).toEqual(['Reasoning · 14 characters', 'view_schedule', 'Reasoning · 15 characters']);
  });
});
