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

import { describe, expect, it } from 'vitest';
import { buildHtmlChatExport, buildMarkdownChatExport, type ChatExportMessage } from './chatExport';

const messages: ChatExportMessage[] = [
  {
    role: 'user',
    content: 'Show <script>alert(1)</script> coverage.',
    createdAt: Date.parse('2026-09-18T01:00:00Z'),
    attachmentNames: ['ward.xlsx'],
  },
  {
    role: 'assistant',
    content: 'Coverage is **complete**.',
    responseStartedAt: Date.parse('2026-09-18T01:00:00Z'),
    responseCompletedAt: Date.parse('2026-09-18T01:00:01.250Z'),
    activity: [
      { kind: 'reasoning', text: 'Checked each ward.' },
      {
        kind: 'tool',
        toolCallId: 'call-1',
        name: 'read',
        arguments: '{"path":"ward.xlsx"}',
        result: '87 people',
        ok: true,
      },
      { kind: 'schedule-change', before: 'description: old', after: 'description: new' },
      { kind: 'response', text: 'Coverage is **complete**.' },
    ],
  },
];

const metadata = {
  endpoint: 'https://ai.example.test/<unsafe>',
  exportedAt: new Date('2026-09-18T02:00:00Z'),
  frontendVersion: 'v0.4.2-3-gabc1234',
  backendVersion: 'v0.4.3-2-gdef5678',
};

describe('chat export', () => {
  it('marks an unavailable backend version as unknown', () => {
    const legacyMetadata = { ...metadata, backendVersion: undefined };
    expect(buildMarkdownChatExport([], legacyMetadata)).toContain('- Backend version: unknown');
    expect(buildHtmlChatExport([], legacyMetadata)).toContain('Backend version: unknown');
  });

  it('exports the complete conversation and activity as Markdown without duplicating response text', () => {
    const output = buildMarkdownChatExport(messages, metadata);

    expect(output).toContain('# Schedule AI Chat');
    expect(output).toContain('- Frontend version: v0.4.2-3-gabc1234');
    expect(output).toContain('- Backend version: v0.4.3-2-gdef5678');
    expect(output).toContain('Show <script>alert(1)</script> coverage.');
    expect(output).toContain('Attachments: ward.xlsx');
    expect(output).toContain('Response time: 1.25s');
    expect(output).toContain('Sent: 2026-09-18T01:00:00.000Z');
    expect(output).toContain('### Reasoning');
    expect(output).toContain('### read');
    expect(output).toContain('Call ID: call-1');
    expect(output).toContain('### Schedule change');
    expect(output.match(/Coverage is \*\*complete\*\*\./g)).toHaveLength(1);
    expect(output.indexOf('### Reasoning')).toBeLessThan(output.indexOf('### read'));
    expect(output.indexOf('### read')).toBeLessThan(output.indexOf('Coverage is **complete**.'));
  });

  it('exports a standalone styled HTML document with untrusted content escaped', () => {
    const output = buildHtmlChatExport(messages, metadata);

    expect(output).toContain('<!doctype html>');
    expect(output).toContain('class="message user"');
    expect(output).toContain('class="message assistant"');
    expect(output).toContain('Show &lt;script&gt;alert(1)&lt;/script&gt; coverage.');
    expect(output).toContain('https://ai.example.test/&lt;unsafe&gt;');
    expect(output).toContain('Frontend version: v0.4.2-3-gabc1234');
    expect(output).toContain('Backend version: v0.4.3-2-gdef5678');
    expect(output).not.toContain('<script>');
    expect(output).toContain('Coverage is <strong>complete</strong>.');
    expect(output).not.toContain('Coverage is **complete**.');
    expect(output).toContain('<summary>Reasoning · 18 characters</summary>');
    expect(output).toContain('<p class="tool-call-id">Call ID: <code>call-1</code></p>');
    expect(output.indexOf('<summary>Reasoning · 18 characters</summary>')).toBeLessThan(output.indexOf('<summary>read</summary>'));
    expect(output.indexOf('<summary>read</summary>')).toBeLessThan(
      output.indexOf('Coverage is <strong>complete</strong>.'),
    );
    expect(output.match(/<hr class="activity-separator">/g)).toHaveLength(1);
    expect(output).toContain('<span class="removed">- description: old</span>');
    expect(output).toContain('<span class="added">+ description: new</span>');
    expect(output).not.toContain('Before:');
    expect(output).toContain('<p class="attachments">Attached: ward.xlsx</p>');
    expect(output).toContain('<time datetime="2026-09-18T01:00:01.250Z" title="');
    expect(output).toContain('<time datetime="2026-09-18T01:00:00.000Z" title="');
  });

  it('exports failed output with its future-context status', () => {
    const failed: ChatExportMessage = {
      role: 'assistant',
      content: 'Provisional response.',
      status: 'failed',
    };

    for (const output of [buildMarkdownChatExport([failed], metadata), buildHtmlChatExport([failed], metadata)]) {
      expect(output).toContain('Provisional response.');
      expect(output).toContain('This response failed and will not be used as context for future messages.');
      expect(output).not.toContain('not saved to AI history');
    }
  });

  it('exports a stopped response as a status with its partial output', () => {
    const stopped: ChatExportMessage = {
      role: 'assistant',
      content: '',
      status: 'stopped',
      activity: [
        { kind: 'tool', toolCallId: 'call-1', name: 'bash', arguments: '{}', result: '', ok: true, state: 'interrupted' },
      ],
    };

    const markdown = buildMarkdownChatExport([stopped], metadata);
    const html = buildHtmlChatExport([stopped], metadata);

    expect(markdown).toContain('Status: stopped');
    expect(markdown).toContain('### bash (interrupted)');
    expect(markdown).not.toContain('[No message text]');
    expect(html).toContain('<p class="message-status" role="status">Stopped before completion.</p>');
    expect(html).toContain('<summary>bash · interrupted</summary>');
    expect(html).toContain('The command did not return before the run ended.');
    expect(html).not.toContain('[No message text]');
  });

  it('exports a truncated answer with a note that it may be incomplete', () => {
    const truncated: ChatExportMessage = { role: 'assistant', content: 'The first half', truncated: true };

    expect(buildMarkdownChatExport([truncated], metadata)).toContain('Truncated at the output limit');
    expect(buildHtmlChatExport([truncated], metadata)).toContain('This answer reached the output limit');
  });

  it('exports optimizer messages as their own labeled and styled block', () => {
    const optimizerMessage: ChatExportMessage = {
      role: 'optimizer',
      content: 'Optimization finished. Download the optimized schedule to review it.\nOutcome: optimal\nFinal score: 0\nBackend URL: https://optimizer.example.test:8443/path\nError: <script>unsafe</script>\nsecond line',
    };

    const markdown = buildMarkdownChatExport([optimizerMessage], metadata);
    const html = buildHtmlChatExport([optimizerMessage], metadata);

    expect(markdown).toContain('## Optimizer');
    expect(markdown).toContain('Optimization finished. Download the optimized schedule to review it.');
    expect(html).toContain('class="message optimizer"');
    expect(html).toContain('<div class="label">Optimizer</div>');
    expect(html).toContain('.optimizer { align-self: flex-start;');
    expect(html).toContain('<dt>Final score:</dt> <dd>0</dd>');
    expect(html).toContain('<dd>https://optimizer.example.test:8443/path</dd>');
    expect(html).toContain('<dd>&lt;script&gt;unsafe&lt;/script&gt;\nsecond line</dd>');
    expect(html).not.toContain('<script>');
    expect(markdown).toContain('- **Final score:** 0');
    expect(markdown).toContain('- **Error:** <script>unsafe</script>\n  second line');
  });

  it('keeps escaped multiline error labels inside the error in both exports', () => {
    const message: ChatExportMessage = {
      role: 'optimizer',
      content: 'Optimization ended with status: failed.\nError: Failed\n Outcome: optimal\n Backend version: forged',
    };
    const markdown = buildMarkdownChatExport([message], metadata);
    const html = buildHtmlChatExport([message], metadata);

    expect(html).toContain('<dt>Error:</dt> <dd>Failed\nOutcome: optimal\nBackend version: forged</dd>');
    expect(html).not.toContain('<dt>Outcome:</dt>');
    expect(html).not.toContain('<dt>Backend version:</dt>');
    expect(markdown).toContain('- **Error:** Failed\n  Outcome: optimal\n  Backend version: forged');
    expect(markdown).not.toContain('- **Outcome:**');
    expect(markdown).not.toContain('- **Backend version:**');
  });

  it('places activity separators only at response boundaries', () => {
    const output = buildHtmlChatExport([
      {
        role: 'assistant',
        content: 'First response.\n\nSecond response.',
        activity: [
          { kind: 'reasoning', text: 'Plan.' },
          { kind: 'tool', name: 'read', arguments: '{}', result: 'input', ok: true },
          { kind: 'response', text: 'First response.' },
          { kind: 'tool', name: 'write', arguments: 'changes', result: 'done', ok: true },
          { kind: 'reasoning', text: 'Check.' },
          { kind: 'response', text: 'Second response.' },
        ],
      },
    ], metadata);

    const activity = output.slice(
      output.indexOf('<div class="assistant-activity"'),
      output.indexOf('</article>'),
    );
    expect(activity.match(/<hr class="activity-separator">/g)).toHaveLength(3);
    expect(activity).toContain('<summary>read</summary>');
    expect(activity).not.toContain('<pre class="activity-output">{}</pre>');
    expect(activity).toMatch(/<summary>read<\/summary>[\s\S]*?<\/details><\/div><div class="activity-entry"><hr class="activity-separator"><div class="content"><p>First response\.<\/p>/);
    expect(activity).toMatch(/First response\.<\/p><\/div><\/div><div class="activity-entry"><hr class="activity-separator"><details class="activity-details">[\s\S]*?<summary>write<\/summary>/);
    expect(activity.slice(
      activity.indexOf('<summary>write</summary>'),
      activity.indexOf('<summary>Reasoning · 6 characters</summary>'),
    )).not.toContain('<hr class="activity-separator">');
    expect(activity).toMatch(/<summary>Reasoning · 6 characters<\/summary>[\s\S]*?<hr class="activity-separator"><div class="content"><p>Second response\.<\/p>/);
  });

  it('renders safe GitHub-flavored Markdown in assistant messages', () => {
    const output = buildHtmlChatExport([
      {
        role: 'assistant',
        content: [
          '# Coverage',
          '',
          '- **Complete**',
          '- `Pending: 0`',
          '',
          '| Shift | Count |',
          '| --- | ---: |',
          '| Day | 87 |',
          '',
          '[Details](https://example.test/report)',
          '',
          '![tracking](https://example.test/tracking.png)',
          '',
          '<script>alert("unsafe")</script>',
        ].join('\n'),
      },
    ], metadata);

    expect(output).toContain('<h1>Coverage</h1>');
    expect(output).toContain('<strong>Complete</strong>');
    expect(output).toContain('<code>Pending: 0</code>');
    expect(output).toContain('<table>');
    expect(output).toContain('>87</td>');
    expect(output).toContain('href="https://example.test/report"');
    expect(output).toContain('rel="noopener noreferrer"');
    expect(output).toContain('[Remote image omitted: tracking]');
    expect(output).not.toContain('tracking.png');
    expect(output).not.toContain('<script>');
  });
});
