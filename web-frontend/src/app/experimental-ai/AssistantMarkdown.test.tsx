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

import { act, fireEvent, render, screen } from '@testing-library/react';
import AssistantMarkdown from './AssistantMarkdown';

describe('AssistantMarkdown', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it('renders common Markdown and GFM structures', () => {
    render(<AssistantMarkdown content={`## Coverage

**Alice** works Monday.

- Day shift

| Person | Shift |
| --- | --- |
| Alice | D |

Use \`minimum_shifts\`.

\`\`\`yaml
people: []
\`\`\`

[Reference](https://example.com)
`} />);

    expect(screen.getByRole('heading', { level: 2, name: 'Coverage' })).toBeInTheDocument();
    expect(screen.getByText('Alice', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByRole('list')).toHaveTextContent('Day shift');
    expect(screen.getByRole('table')).toHaveTextContent('AliceD');
    expect(screen.getByText('minimum_shifts', { selector: 'code' })).toBeInTheDocument();
    expect(screen.getByText('people: []', { selector: 'code' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reference' })).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: 'Reference' })).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('copies fenced code without adding a button to inline code', async () => {
    vi.useFakeTimers();
    render(<AssistantMarkdown content={`Use \`minimum_shifts\`.

\`\`\`yaml
people: []
\`\`\`
`} />);

    const copyButton = screen.getByRole('button', { name: 'Copy code' });
    expect(screen.getAllByRole('button')).toHaveLength(1);
    fireEvent.click(copyButton);
    await act(async () => {
      await Promise.resolve();
    });

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('people: []');
    expect(screen.getByRole('button', { name: 'Copied' })).toHaveAttribute('title', 'Copied');

    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByRole('button', { name: 'Copy code' })).toHaveAttribute('title', 'Copy code');
    vi.useRealTimers();
  });

  it('does not execute raw HTML or load remote Markdown images', () => {
    const { container } = render(<AssistantMarkdown content={`Before

<script>alert('unsafe')</script>

[unsafe link](javascript:alert('unsafe'))

![tracker](https://tracker.example/pixel.png)
`} />);

    const unsafeLink = screen.getByText('unsafe link').closest('a');
    expect(container.querySelector('script')).not.toBeInTheDocument();
    expect(container.querySelector('img')).not.toBeInTheDocument();
    expect(screen.queryByText("alert('unsafe')")).not.toBeInTheDocument();
    expect(unsafeLink?.getAttribute('href') ?? '').not.toMatch(/^javascript:/i);
    expect(screen.getByText('[Remote image omitted: tracker]')).toBeInTheDocument();
  });
});
