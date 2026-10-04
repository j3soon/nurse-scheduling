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
import { activitySummary, formatCharacterCount, formatResponseDuration, scheduleChangeLines } from './chatPresentation';
import { parseOptimizerMessage } from './optimizerMessage';

// Bubbles follow the provider request roles. A user-role message that the app wrote has a source.
// The optimizer role is an app notice with the run summary. The model receives its own optimizer message.
export interface ChatExportMessage {
  role: 'system' | 'user' | 'assistant' | 'optimizer';
  source?: 'app' | 'status' | 'optimizer';
  // Topic of an app event or status message, shown after its role label.
  title?: string;
  content: string;
  createdAt?: number;
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
  backendVersion?: string;
  // A proposal waiting for approval is not part of the transcript, so exports add it separately.
  pendingProposalDiff?: string;
  // A background optimization still running at export time. Its score changes, so exports omit it.
  runningOptimization?: { jobId: string; state: string; solver?: string; timeoutSeconds?: number };
  // Files kept in the chat session at export time. The export lists them without their contents.
  uploadedFiles?: { filename: string; bytes: number }[];
}

type ChatExportSessionState = Pick<
  ChatExportMetadata, 'backendVersion' | 'pendingProposalDiff' | 'runningOptimization' | 'uploadedFiles'
>;

function uploadedFileLines(files: NonNullable<ChatExportMetadata['uploadedFiles']>): string[] {
  return files.map(file => `${file.filename} (${(file.bytes / 1000).toLocaleString('en-US')} KB)`);
}

const RUNNING_OPTIMIZATION_NOTE = 'An optimization was still running when this chat was exported. Its result is not included.';

function runningOptimizationDetails(running: NonNullable<ChatExportMetadata['runningOptimization']>): string[] {
  return [
    `Job: ${running.jobId}`,
    `State: ${running.state}`,
    ...(running.solver ? [`Solver: ${running.solver}`] : []),
    ...(running.timeoutSeconds !== undefined ? [`Solver timeout: ${running.timeoutSeconds}s`] : []),
  ];
}

const PENDING_PROPOSAL_NOTE = 'This change is waiting for approval in the app. The current schedule has not changed.';

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

function renderScheduleChangeHtml(entry: Extract<ActivityEntry, { kind: 'schedule-change' }>): string {
  const lines = scheduleChangeLines(entry.before, entry.after);
  const removed = lines.removed
    .map(line => `<span class="removed">- ${escapeHtml(line)}</span>`)
    .join('');
  const added = lines.added
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
      ? '<p class="interrupted">The command did not return before the run ended.</p>'
      : '';
    body = `<div class="tool-body">${callId}${argumentsOutput}${resultOutput}${interrupted}</div>`;
  }
  return `<details class="activity-details">
            <summary>${escapeHtml(activitySummary(entry))}</summary>
            <div class="activity-body">${body}</div>
          </details>`;
}

export function messageLabel(message: ChatExportMessage): string {
  if (message.role === 'system') return 'System';
  if (message.role === 'assistant') return 'Assistant';
  if (message.role === 'optimizer') return 'Optimizer';
  const topic = message.title ? ` - ${message.title}` : '';
  if (message.source === 'app') return `User · App${topic}`;
  if (message.source === 'status') return `User · Status${topic}`;
  if (message.source === 'optimizer') return 'User · Optimizer';
  return 'User';
}

// A fence longer than any backtick run in the text keeps the block intact.
function fencedText(text: string): string[] {
  const longestRun = Math.max(0, ...(text.match(/`+/g) ?? []).map(run => run.length));
  const fence = '`'.repeat(Math.max(3, longestRun + 1));
  return [`${fence}text`, text, fence];
}

function messageDetails(message: ChatExportMessage): string[] {
  const details: string[] = [];
  if (message.createdAt !== undefined) details.push(`Sent: ${new Date(message.createdAt).toISOString()}`);
  if (message.status) details.push(`Status: ${message.status}`);
  if (message.status === 'failed') {
    details.push('This response failed and will not be used as context for future messages.');
  }
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
  const status = message.status === 'pending' && !message.content
    ? '<p class="message-status" role="status">Thinking</p>'
    : message.status === 'failed'
      ? '<p class="failure">This response failed and will not be used as context for future messages.</p>'
      : message.status === 'stopped'
        ? '<p class="message-status" role="status">Stopped before completion.</p>'
        : '';
  const truncated = message.truncated
    ? '<p class="message-status" role="status">This answer reached the output limit and may be incomplete.</p>'
    : '';
  const timestamp = message.responseCompletedAt ?? message.createdAt;
  const duration = message.responseStartedAt !== undefined && message.responseCompletedAt !== undefined
    ? ` · ${formatResponseDuration(message.responseStartedAt, message.responseCompletedAt)}`
    : '';
  const timing = timestamp !== undefined
    ? `<time datetime="${new Date(timestamp).toISOString()}" title="${escapeHtml(new Date(timestamp).toLocaleString())}">${escapeHtml(new Date(timestamp).toLocaleString())}${duration}</time>`
    : '';
  return `${status}${truncated}${timing}`;
}

function renderOptimizerHtml(content: string): string {
  const { summary, details } = parseOptimizerMessage(content);
  const rows = details.map(({ label, value }) => `<div><dt>${escapeHtml(label)}:</dt> <dd>${escapeHtml(value)}</dd></div>`).join('');
  return `<div class="content">${escapeHtml(summary || '[No message text]')}</div>${rows ? `<dl class="optimizer-details">${rows}</dl>` : ''}`;
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
    `- Backend version: ${metadata.backendVersion ?? 'unknown'}`,
    `- AI server: ${metadata.endpoint}`,
  ];
  messages.forEach(message => {
    lines.push('', `## ${messageLabel(message)}`);
    if (message.role === 'optimizer') {
      const { summary, details } = parseOptimizerMessage(message.content);
      lines.push('', summary || '[No message text]');
      if (details.length) lines.push('', ...details.map(({ label, value }) => `- **${label}:** ${value.replaceAll('\n', '\n  ')}`));
    } else if (message.role === 'system' || message.source !== undefined) {
      lines.push('', ...fencedText(message.content));
    } else if (message.role === 'user') {
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
  if (metadata.uploadedFiles?.length) {
    lines.push('', '## Uploaded files', '', ...uploadedFileLines(metadata.uploadedFiles).map(line => `- ${line}`));
  }
  if (metadata.runningOptimization !== undefined) {
    lines.push(
      '', '## Optimization running', '', RUNNING_OPTIMIZATION_NOTE, '',
      ...runningOptimizationDetails(metadata.runningOptimization).map(detail => `- ${detail}`),
    );
  }
  if (metadata.pendingProposalDiff !== undefined) {
    lines.push('', '## Pending proposal', '', PENDING_PROPOSAL_NOTE, '', ...fencedText(metadata.pendingProposalDiff));
  }
  return `${lines.join('\n')}\n`;
}

export function buildHtmlChatExport(
  messages: ChatExportMessage[],
  metadata: ChatExportMetadata,
): string {
  const renderedMessages = messages.map(message => {
    const timeline = message.role === 'assistant'
      ? renderAssistantTimelineHtml(message)
      : message.role === 'system' || message.source !== undefined
        ? `<details class="system-prompt"><summary>${formatCharacterCount(message.content.length)} characters</summary><pre>${escapeHtml(message.content)}</pre></details>`
        : message.role === 'optimizer'
          ? renderOptimizerHtml(message.content)
          : `<div class="content">${escapeHtml(message.content || '[No message text]')}</div>`;
    return `
      <article class="message ${message.role}${message.source ? ` ${message.source}` : ''}">
        <div class="label">${escapeHtml(messageLabel(message))}</div>
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
    :root { color-scheme: light; font-family: ui-sans-serif, -apple-system, system-ui, Segoe UI, Helvetica, Apple Color Emoji, Arial, sans-serif, Segoe UI Emoji, Segoe UI Symbol; color: #111827; }
    body { margin: 0; background: white; }
    main { box-sizing: border-box; max-width: 1024px; margin: 0 auto; padding: 32px 16px; }
    main > h1 { margin: 0 0 8px; font-size: 30px; line-height: 36px; font-weight: 700; }
    .metadata { margin: 0 0 32px; color: #6b7280; font-size: 13px; }
    .proposal { margin-top: 24px; border: 1px solid #bfdbfe; border-radius: 12px; background: #eff6ff; padding: 16px; color: #1e3a8a; }
    .proposal h2 { margin: 0 0 8px; font-size: 16px; }
    .proposal p { margin: 0 0 8px; font-size: 13px; }
    .proposal ul { margin: 0; padding-left: 20px; font-size: 13px; }
    .proposal pre { max-height: 480px; overflow: auto; margin: 0; border-radius: 8px; background: white; padding: 12px; color: #1f2937; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.625 ui-monospace, monospace; }
    .chat { display: flex; flex-direction: column; gap: 16px; border: 1px solid #e5e7eb; border-radius: 12px; background: #f9fafb; padding: 16px; }
    .message { box-sizing: border-box; width: 85%; min-width: 0; max-width: 85%; padding: 12px 16px; border-radius: 12px; }
    .user { align-self: flex-end; background: #155dfc; color: white; }
    .assistant { align-self: flex-start; border: 1px solid #e5e7eb; background: white; }
    .optimizer { align-self: flex-start; border: 1px solid #a7f3d0; background: #ecfdf5; color: #022c22; }
    .optimizer-details { display: grid; gap: 6px; margin: 12px 0 0; font-size: 14px; line-height: 20px; overflow-wrap: anywhere; }
    .optimizer-details dt { display: inline; font-weight: 600; }
    .optimizer-details dd { display: inline; margin: 0; white-space: pre-wrap; }
    .system { align-self: stretch; width: auto; max-width: none; border: 1px dashed #d1d5db; background: #f9fafb; color: #374151; }
    .user.app, .user.status, .user.optimizer { border: 1px solid #bfdbfe; background: #eff6ff; color: #1e3a8a; font: 12px/1.625 ui-monospace, monospace; }
    .user.optimizer { align-self: flex-start; border-color: #a7f3d0; background: #ecfdf5; color: #022c22; }
    .label { margin-bottom: 4px; font-size: 12px; font-weight: 600; letter-spacing: .025em; text-transform: uppercase; opacity: .7; }
    .content { overflow-wrap: anywhere; line-height: 1.5rem; }
    .user .content, .optimizer .content { white-space: pre-wrap; }
    .user.app .content, .user.status .content { line-height: 1.625; }
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
    .system-prompt { color: #4b5563; font-size: 12px; }
    .system-prompt summary { cursor: pointer; }
    .system-prompt pre { max-height: 288px; overflow: auto; margin: 4px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.625 ui-monospace, monospace; }
    .activity-body { margin-top: 4px; border-radius: 4px; background: #f9fafb; padding: 8px; }
    .activity-output, .schedule-diff { max-height: 288px; overflow: auto; margin: 0; color: #4b5563; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.625 ui-monospace, monospace; }
    .tool-body { display: flex; flex-direction: column; gap: 8px; }
    .schedule-diff .removed, .schedule-diff .added { display: block; }
    .schedule-diff .removed { color: #b91c1c; }
    .schedule-diff .added { color: #15803d; }
    .interrupted { margin: 0; color: #b91c1c; font-size: 12px; }
    .tool-call-id { margin: 0; color: #6b7280; font-size: 11px; }
    .message-status { margin: 0; color: #4b5563; }
    .failure { margin: 12px 0 0; border-top: 1px solid #fecaca; padding-top: 12px; color: #b91c1c; font-size: 14px; }
    time { display: block; margin-top: 8px; color: #6b7280; font-size: 11px; line-height: 1rem; }
    .user time { color: #eff6ff; }
    @media (min-width: 640px) { main { padding-right: 24px; padding-left: 24px; } }
    @media print { body { background: white; } main { padding: 0; } .message { break-inside: avoid; } }
  </style>
</head>
<body>
  <main>
    <h1>Schedule AI Chat</h1>
    <p class="metadata">Exported ${escapeHtml(metadata.exportedAt.toISOString())}<br>Frontend version: ${escapeHtml(metadata.frontendVersion)}<br>Backend version: ${escapeHtml(metadata.backendVersion ?? 'unknown')}<br>AI server: ${escapeHtml(metadata.endpoint)}</p>
    <section class="chat" aria-label="Chat transcript">${renderedMessages}
    </section>${!metadata.uploadedFiles?.length ? '' : `
    <section class="proposal" aria-label="Uploaded files">
      <h2>Uploaded files</h2>
      <ul>${uploadedFileLines(metadata.uploadedFiles).map(line => `<li>${escapeHtml(line)}</li>`).join('')}</ul>
    </section>`}${metadata.runningOptimization === undefined ? '' : `
    <section class="proposal" aria-label="Optimization running">
      <h2>Optimization running</h2>
      <p>${RUNNING_OPTIMIZATION_NOTE}</p>
      <ul>${runningOptimizationDetails(metadata.runningOptimization).map(detail => `<li>${escapeHtml(detail)}</li>`).join('')}</ul>
    </section>`}${metadata.pendingProposalDiff === undefined ? '' : `
    <section class="proposal" aria-label="Pending proposal">
      <h2>Pending proposal</h2>
      <p>${PENDING_PROPOSAL_NOTE}</p>
      <pre>${escapeHtml(metadata.pendingProposalDiff)}</pre>
    </section>`}
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
  sessionState: ChatExportSessionState = {},
): string {
  const metadata = { endpoint, exportedAt, frontendVersion: CURRENT_APP_VERSION, ...sessionState };
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
  return url;
}
