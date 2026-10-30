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
  it('converts prose by default and restores exact originals without changing literal text', () => {
    const content = '软件和鼠标。**数据库**\n\n`软件`\n\n```yaml\n名字: 张三\n```\n\n> 软件原文\n\n[软件链接](https://example.test/软件)';
    const { container, rerender } = render(<AssistantMarkdown content={content} />);
    expect(screen.getByText('軟體和滑鼠。', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('資料庫')).toBeInTheDocument();
    expect(container.querySelector('blockquote')).toHaveTextContent('软件原文');
    expect(container.querySelector('a')).toHaveTextContent('软件链接');
    expect(container.querySelector('a')).toHaveAttribute('href', encodeURI('https://example.test/软件'));
    expect(container.querySelector('pre')).toHaveTextContent('名字: 张三');
    expect(container.querySelector('code')).toHaveTextContent('软件');
    rerender(<AssistantMarkdown content={content} convertChinese={false} />);
    expect(screen.getByText('软件和鼠标。', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('数据库')).toBeInTheDocument();
    rerender(<AssistantMarkdown content={content} />);
    expect(screen.getByText('資料庫')).toBeInTheDocument();
  });

  it('reconverts the accumulated message when a streamed phrase completes', () => {
    const { rerender } = render(<AssistantMarkdown content="数据" />);
    rerender(<AssistantMarkdown content="数据库" />);
    expect(screen.getByText('資料庫')).toBeInTheDocument();
  });

});
