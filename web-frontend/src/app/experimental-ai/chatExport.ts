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

// This code is mostly AI generated.

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CURRENT_APP_VERSION } from '@/utils/version';
import type { ActivityEntry } from './AssistantActivity';

export interface ChatExportMessage {
  role: 'user' | 'assistant' | 'optimizer';
  content: string;
  attachmentNames?: string[];
  activity?: ActivityEntry[];
  status?: 'pending' | 'failed' | 'stopped';
  // The answer stopped at the model's output limit and may be incomplete.
  truncated?: boolean;
  responseStartedAt?: number;
  responseCompletedAt?: number;
}

interface ChatExportMetadata {
  endpoint: string;
  exportedAt: Date;
  frontendVersion: string;
}

export type ChatExportFormat = 'html' | 'markdown';

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

const exportMarkdownComponents: Components = {
  a: ({ children, href }) => {
    const external = href?.startsWith('http://') || href?.startsWith('https://');
    return createElement(
      'a',
      {
        href,
        target: external ? '_blank' : undefined,
        rel: external ? 'noopener noreferrer' : undefined,
      },
      children,
    );
  },
  img: ({ alt }) => createElement(
    'span',
    { className: 'remote-image-omitted' },
    `[Remote image omitted${alt ? `: ${alt}` : ''}]`,
  ),
};

function renderMarkdownHtml(value: string): string {
  return renderToStaticMarkup(createElement(
    Markdown,
    {
      remarkPlugins: [remarkGfm],
      skipHtml: true,
      components: exportMarkdownComponents,
    },
    value || '[No message text]',
  ));
}

function activityLabel(entry: ActivityEntry): string {
  if (entry.kind === 'response') return 'Response';
  if (entry.kind === 'reasoning') return 'Reasoning';
  if (entry.kind === 'schedule-change') return 'Schedule change';
  if (entry.state === 'running') return `${entry.name} (running)`;
  if (entry.state === 'interrupted') return `${entry.name} (interrupted)`;
  return entry.ok ? entry.name : `${entry.name} (failed)`;
}

function activityText(entry: ActivityEntry): string {
  if (entry.kind === 'reasoning' || entry.kind === 'response') return entry.text;
  if (entry.kind === 'schedule-change') return `Before:\n${entry.before}\n\nAfter:\n${entry.after}`;
  return [
    entry.toolCallId ? `Call ID: ${entry.toolCallId}` : '',
    entry.arguments ? `Arguments:\n${entry.arguments}` : '',
    entry.result ? `Result:\n${entry.result}` : '',
  ].filter(Boolean).join('\n\n');
}

function formatCount(characters: number): string {
  return characters >= 1000 ? `${(characters / 1000).toFixed(1)}k` : `${characters}`;
}

function formatResponseDuration(startedAt: number, completedAt: number): string {
  const seconds = Math.max(0, completedAt - startedAt) / 1000;
  if (seconds < 1) return '<1s';
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function activitySummary(entry: Exclude<ActivityEntry, { kind: 'response' }>): string {
  if (entry.kind === 'reasoning') return `Reasoning · ${formatCount(entry.text.length)} characters`;
  if (entry.kind === 'schedule-change') return 'schedule edit';
  if (entry.state === 'running') return `${entry.name} · running`;
  if (entry.state === 'interrupted') return `${entry.name} · interrupted`;
  return entry.ok ? entry.name : `${entry.name} · failed`;
}

function renderScheduleChangeHtml(entry: Extract<ActivityEntry, { kind: 'schedule-change' }>): string {
  const before = entry.before.split('\n');
  const after = entry.after.split('\n');
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < before.length - prefix
    && suffix < after.length - prefix
    && before[before.length - suffix - 1] === after[after.length - suffix - 1]
  ) suffix += 1;
  const removed = before.slice(prefix, before.length - suffix)
    .map(line => `<span class="removed">- ${escapeHtml(line)}</span>`)
    .join('');
  const added = after.slice(prefix, after.length - suffix)
    .map(line => `<span class="added">+ ${escapeHtml(line)}</span>`)
    .join('');
  return `<pre class="schedule-diff">${removed}${added}</pre>`;
}

function renderActivityDetailsHtml(entry: Exclude<ActivityEntry, { kind: 'response' }>): string {
  let body: string;
  if (entry.kind === 'reasoning') {
    body = `<pre class="activity-output">${escapeHtml(entry.text)}</pre>`;
  } else if (entry.kind === 'schedule-change') {
    body = renderScheduleChangeHtml(entry);
  } else {
    const callId = entry.toolCallId
      ? `<p class="tool-call-id">Call ID: <code>${escapeHtml(entry.toolCallId)}</code></p>`
      : '';
    const argumentsOutput = entry.arguments && entry.arguments !== '{}'
      ? `<pre class="activity-output">${escapeHtml(entry.arguments)}</pre>`
      : '';
    const resultOutput = entry.result
      ? `<pre class="activity-output">${escapeHtml(entry.result)}</pre>`
      : '';
    const interrupted = entry.state === 'interrupted' && !entry.result
      ? '<p class="interrupted">The command did not return before the turn ended.</p>'
      : '';
    body = `<div class="tool-body">${callId}${argumentsOutput}${resultOutput}${interrupted}</div>`;
  }
  return `<details class="activity-details">
            <summary>${escapeHtml(activitySummary(entry))}</summary>
            <div class="activity-body">${body}</div>
          </details>`;
}

function messageDetails(message: ChatExportMessage): string[] {
  const details: string[] = [];
  if (message.attachmentNames?.length) details.push(`Attachments: ${message.attachmentNames.join(', ')}`);
  if (message.status) details.push(`Status: ${message.status}`);
  if (message.truncated) details.push('Truncated at the output limit');
  if (message.responseCompletedAt !== undefined) {
    details.push(`Completed: ${new Date(message.responseCompletedAt).toISOString()}`);
  }
  if (message.responseStartedAt !== undefined && message.responseCompletedAt !== undefined) {
    details.push(`Response time: ${Math.max(0, message.responseCompletedAt - message.responseStartedAt) / 1000}s`);
  }
  return details;
}

function assistantTimeline(message: ChatExportMessage): ActivityEntry[] {
  const activity = message.activity ?? [];
  if (activity.some(entry => entry.kind === 'response')) return activity;
  if (!message.content && message.status === 'stopped') return activity;
  return [
    ...activity,
    { kind: 'response', text: message.content || '[No message text]' },
  ];
}

function htmlAssistantTimeline(message: ChatExportMessage): ActivityEntry[] {
  const activity = message.activity ?? [];
  if (activity.some(entry => entry.kind === 'response')) return activity;
  if (message.content) return [...activity, { kind: 'response', text: message.content }];
  if (message.status !== undefined) return activity;
  return [...activity, { kind: 'response', text: '[No message text]' }];
}

function renderAssistantTimelineHtml(message: ChatExportMessage): string {
  const entries = htmlAssistantTimeline(message);
  const activity = entries.map((entry, index) => {
    const previous = entries[index - 1];
    const separator = index > 0 && (entry.kind === 'response' || previous.kind === 'response')
      ? '<hr class="activity-separator">'
      : '';
    const content = entry.kind === 'response'
      ? `<div class="content">${renderMarkdownHtml(entry.text)}</div>`
      : renderActivityDetailsHtml(entry);
    return `<div class="activity-entry">${separator}${content}</div>`;
  }).join('');
  return `<div class="assistant-activity" aria-label="Assistant activity">${activity}</div>`;
}

function renderHtmlMessageDetails(message: ChatExportMessage): string {
  const attachments = message.attachmentNames?.length
    ? `<p class="attachments">Attached: ${escapeHtml(message.attachmentNames.join(', '))}</p>`
    : '';
  const status = message.status === 'pending' && !message.content
    ? '<p class="message-status" role="status">Thinking</p>'
    : message.status === 'failed'
      ? '<p class="failure">This turn failed and was not saved to AI history.</p>'
      : message.status === 'stopped'
        ? '<p class="message-status" role="status">Stopped before completion.</p>'
        : '';
  const truncated = message.truncated
    ? '<p class="message-status" role="status">This answer reached the output limit and may be incomplete.</p>'
    : '';
  const timing = message.responseStartedAt !== undefined && message.responseCompletedAt !== undefined
    ? `<time datetime="${new Date(message.responseCompletedAt).toISOString()}">${escapeHtml(new Date(message.responseCompletedAt).toLocaleString())} · ${formatResponseDuration(message.responseStartedAt, message.responseCompletedAt)}</time>`
    : '';
  return `${attachments}${status}${truncated}${timing}`;
}

export function buildMarkdownChatExport(
  messages: ChatExportMessage[],
  metadata: ChatExportMetadata,
): string {
  const lines = [
    '# Schedule AI Chat',
    '',
    `- Exported: ${metadata.exportedAt.toISOString()}`,
    `- Frontend version: ${metadata.frontendVersion}`,
    `- AI server: ${metadata.endpoint}`,
  ];
  messages.forEach(message => {
    lines.push('', `## ${message.role === 'user' ? 'You' : message.role === 'optimizer' ? 'Optimizer' : 'Assistant'}`);
    if (message.role !== 'assistant') {
      lines.push('', message.content || '[No message text]');
    } else {
      assistantTimeline(message).forEach(entry => {
        if (entry.kind === 'response') {
          lines.push('', entry.text || '[No message text]');
        } else {
          lines.push('', `### ${activityLabel(entry)}`, '', '```text', activityText(entry), '```');
        }
      });
    }
    const details = messageDetails(message);
    if (details.length) lines.push('', ...details.map(detail => `- ${detail}`));
  });
  return `${lines.join('\n')}\n`;
}

export function buildHtmlChatExport(
  messages: ChatExportMessage[],
  metadata: ChatExportMetadata,
): string {
  const renderedMessages = messages.map(message => {
    const timeline = message.role === 'assistant'
      ? renderAssistantTimelineHtml(message)
      : `<div class="content">${escapeHtml(message.content || '[No message text]')}</div>`;
    return `
      <article class="message ${message.role}">
        <div class="label">${message.role === 'user' ? 'You' : message.role === 'optimizer' ? 'Optimizer' : 'Assistant'}</div>
        ${timeline}
        ${renderHtmlMessageDetails(message)}
      </article>`;
  }).join('');
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Schedule AI Chat</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #111827; }
    body { margin: 0; background: white; }
    main { box-sizing: border-box; max-width: 960px; margin: 0 auto; padding: 40px 24px; }
    main > h1 { margin: 0 0 8px; font-size: 28px; }
    .metadata { margin: 0 0 32px; color: #6b7280; font-size: 13px; }
    .chat { display: flex; flex-direction: column; gap: 16px; border: 1px solid #e5e7eb; border-radius: 12px; background: #f9fafb; padding: 16px; }
    .message { box-sizing: border-box; width: fit-content; max-width: 85%; padding: 12px 16px; border-radius: 12px; }
    .user { align-self: flex-end; background: #2563eb; color: white; }
    .assistant { align-self: flex-start; border: 1px solid #e5e7eb; background: white; }
    .optimizer { align-self: flex-start; border: 1px solid #a7f3d0; background: #ecfdf5; color: #022c22; }
    .label { margin-bottom: 4px; font-size: 12px; font-weight: 600; letter-spacing: .025em; text-transform: uppercase; opacity: .7; }
    .content { overflow-wrap: anywhere; line-height: 1.5rem; }
    .user .content, .optimizer .content { white-space: pre-wrap; }
    .content > :first-child { margin-top: 0; }
    .content > :last-child { margin-bottom: 0; }
    .content h1, .content h2 { margin: 16px 0 8px; line-height: 1.25; font-weight: 600; }
    .content h3, .content h4, .content h5, .content h6 { margin: 12px 0 6px; line-height: 1.25; font-weight: 600; }
    .content h1 { font-size: 20px; }
    .content h2 { font-size: 18px; }
    .content h3 { font-size: 16px; }
    .content p { white-space: pre-wrap; }
    .content ul, .content ol { margin: 0 0 8px 20px; padding: 0; }
    .content li + li { margin-top: 4px; }
    .content pre { overflow-x: auto; border-radius: 8px; background: #111827; padding: 12px; color: #f3f4f6; }
    .content code { border-radius: 4px; background: #f3f4f6; padding: 2px 4px; font: .9em ui-monospace, monospace; }
    .content pre code { background: transparent; padding: 0; color: inherit; }
    .content blockquote { margin-left: 0; border-left: 4px solid #d1d5db; padding-left: 12px; color: #4b5563; }
    .content table { width: 100%; border-collapse: collapse; }
    .content th, .content td { border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; }
    .content th { background: #f3f4f6; }
    .content hr { margin: 12px 0; border: 0; border-top: 1px solid #d1d5db; }
    .content a { color: #1d4ed8; text-decoration: underline; }
    .remote-image-omitted { border-radius: 4px; background: #f3f4f6; padding: 2px 6px; color: #4b5563; }
    .activity-separator { margin: 12px 0; border: 0; border-top: 1px solid #e5e7eb; }
    .activity-details { color: #6b7280; font-size: 12px; }
    .activity-details summary { cursor: pointer; padding: 2px 0; }
    .activity-body { margin-top: 4px; border-radius: 4px; background: #f9fafb; padding: 8px; }
    .activity-output, .schedule-diff { max-height: 288px; overflow: auto; margin: 0; color: #4b5563; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.625 ui-monospace, monospace; }
    .tool-body { display: flex; flex-direction: column; gap: 8px; }
    .schedule-diff .removed, .schedule-diff .added { display: block; }
    .schedule-diff .removed { color: #b91c1c; }
    .schedule-diff .added { color: #15803d; }
    .interrupted { margin: 0; color: #b91c1c; font-size: 12px; }
    .tool-call-id { margin: 0; color: #6b7280; font-size: 11px; }
    .attachments { margin: 8px 0 0; font-size: 12px; opacity: .8; }
    .message-status { margin: 0; color: #4b5563; }
    .failure { margin: 12px 0 0; border-top: 1px solid #fecaca; padding-top: 12px; color: #b91c1c; font-size: 14px; }
    time { display: block; margin-top: 8px; color: #9ca3af; font-size: 11px; }
    @media print { body { background: white; } main { padding: 0; } .message { break-inside: avoid; } }
  </style>
</head>
<body>
  <main>
    <h1>Schedule AI Chat</h1>
    <p class="metadata">Exported ${escapeHtml(metadata.exportedAt.toISOString())}<br>Frontend version: ${escapeHtml(metadata.frontendVersion)}<br>AI server: ${escapeHtml(metadata.endpoint)}</p>
    <section class="chat" aria-label="Chat transcript">${renderedMessages}
    </section>
  </main>
</body>
</html>
`;
}

export function downloadChatExport(
  format: ChatExportFormat,
  messages: ChatExportMessage[],
  endpoint: string,
  exportedAt = new Date(),
): void {
  const metadata = { endpoint, exportedAt, frontendVersion: CURRENT_APP_VERSION };
  const content = format === 'html'
    ? buildHtmlChatExport(messages, metadata)
    : buildMarkdownChatExport(messages, metadata);
  const extension = format === 'html' ? 'html' : 'md';
  const type = format === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8';
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `schedule-ai-chat-${exportedAt.toISOString().slice(0, 10)}.${extension}`;
  link.click();
  URL.revokeObjectURL(url);
}
