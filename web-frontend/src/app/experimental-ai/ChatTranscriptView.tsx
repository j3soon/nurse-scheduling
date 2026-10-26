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

import '../../../../core/nurse_scheduling/ai/chat_styles.css';

import { FiDownload } from 'react-icons/fi';

import { AssistantActivity, CompactionSummary } from './AssistantActivity';
import { CostDetails } from './CostDetails';
import CollapsedText from './CollapsedText';
import { characterCount, messageLabel, messageUploadedFileLines, transcriptConversation } from './chatPresentation';
import { formatResponseDuration, formatResponseTime, formatSessionExpiration, retentionLabel } from './chatPresentation';
import { parseOptimizerMessage } from './optimizerMessage';

import type { ChatMessage } from './chatTranscript';

function ThinkingIndicator() {
  return (
    <span role="status" aria-label="Thinking" className="thinking">
      <span>Thinking</span>
      <span aria-hidden="true" className="thinking-dots">
        {[0, 1, 2].map(index => (
          <span
            key={index}
            className="thinking-dot"
            style={{ animationDelay: `${index * 160}ms` }}
          />
        ))}
      </span>
    </span>
  );
}

interface ChatTranscriptViewProps {
  messages: ChatMessage[];
  showReasoning: boolean;
  showTools: boolean;
  showCosts: boolean;
  showModels: boolean;
  steeringAssistantId: string | null;
  conversationUnavailable: boolean;
  removingDownloadId: string | null;
  downloadingOptimizationId: string | null;
  downloadGeneratedFiles: (id: string) => Promise<void>;
  removeGeneratedFiles: (id: string) => Promise<void>;
  downloadOptimizationResult: (id: string) => Promise<void>;
  activeSessionId: string | null;
  sessionExpiresAt: number | null;
  sessionRetentionSeconds: number;
}

/** Render the transcript with the same activity and failure notices as the page. */
export function ChatTranscriptView({
  messages,
  showReasoning,
  showTools,
  showCosts,
  showModels,
  steeringAssistantId,
  conversationUnavailable,
  removingDownloadId,
  downloadingOptimizationId,
  downloadGeneratedFiles,
  removeGeneratedFiles,
  downloadOptimizationResult,
  activeSessionId,
  sessionExpiresAt,
  sessionRetentionSeconds,
}: ChatTranscriptViewProps) {
  const bubbles = transcriptConversation(messages).map((part, index) => ({
    message: part, key: `${part.id}-${index}`,
  }));
  return (
      <section
        aria-label="Chat messages"
        aria-live="polite"
        className="chat mb-4 min-h-80"
      >
        {messages.length === 0 && (
          <div className="flex min-h-72 items-center justify-center text-center text-gray-500">
            <p>Try asking “Who is available on the first date?”</p>
          </div>
        )}
        {bubbles.map(({ message, key }) => {
          const notice = message.presentation === 'notice';
          const summary = message.presentation === 'summary' ? message.compaction : undefined;
          const centered = notice || summary?.invalidated || message.role === 'optimizer';
          const alignment = centered ? 'mx-auto' : message.role === 'assistant' ? 'mr-auto' : 'ml-auto';
          const classes = ['message', message.role, message.source,
            notice || summary?.invalidated ? 'app-notice' : undefined, alignment].filter(Boolean).join(' ');
          const uploads = messageUploadedFileLines(message);
          const timestamp = message.responseCompletedAt ?? message.createdAt;
          const optimizer = message.role === 'optimizer' ? parseOptimizerMessage(message.content) : null;
          return (
            <article
              key={key}
              className={classes}
            >
              <p className="label">{notice ? 'App notice'
                : summary ? summary.invalidated ? 'Discarded conversation summary' : 'User · Conversation summary' : messageLabel(message)}</p>
              {/* Messages reach the model by default, so only exceptions get a status line. */}
              {(notice || summary?.invalidated || message.role === 'optimizer' || message.compacted) && (
                <p className="message-status">
                  {summary?.invalidated ? 'Omitted from future model context.'
                    : message.compacted ? 'Compacted out of context.' : 'Not sent to AI.'}
                </p>
              )}
              {summary && <details className="system-prompt">
                <summary className="collapsed-summary">Conversation summary</summary>
                <CompactionSummary entry={summary} />
              </details>}
              {uploads.length > 0 && (
                <ul aria-label="Uploaded files in this message" className="attachments">
                  {uploads.map((file, index) => <li key={index}>{file}</li>)}
                </ul>
              )}
              {message.activity && (
                <AssistantActivity
                  entries={message.activity.filter(entry => (
                    entry.kind === 'notice' || entry.kind === 'response' || entry.kind === 'schedule-applied' || entry.kind === 'schedule-check'
                      || entry.kind === 'compaction'
                      || (entry.kind === 'reasoning' ? showReasoning : showTools)
                  ))}
                />
              )}
              {summary ? null : notice ? null : message.presentation === 'context' ? (
                <p className="context-content">{message.content}</p>
              ) : message.role === 'assistant' && !message.content && message.status === 'pending' ? (
                message.activity?.some(entry => entry.kind === 'compaction' && entry.state === 'running') ? null
                  : steeringAssistantId === message.id ? <p className="text-xs text-gray-500">Steering…</p> : <ThinkingIndicator />
              ) : message.role === 'system' ? (
                <CollapsedText summary={`${characterCount(message.content).toLocaleString('en-US')} characters`} text={message.content} />
              ) : message.source !== undefined ? (
                // The label names the topic, so the exact text starts collapsed.
                <CollapsedText summary={`${characterCount(message.content).toLocaleString('en-US')} characters`} text={message.content} />
              ) : message.role === 'user' ? (
                <p className="plain-content">{message.content}</p>
              ) : optimizer ? (
                <>
                  <p className="plain-content">{optimizer.summary}</p>
                  {optimizer.details.length > 0 && (
                    <dl className="optimizer-details">
                      {optimizer.details.map(({ label, value }, index) => (
                        <div key={`${label}-${index}`} className="optimizer-detail">
                          <dt className="optimizer-label">{label}:</dt>{' '}
                          <dd className="optimizer-value">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </>
              ) : null}
              {message.role === 'optimizer' && message.optimizerJob?.downloadable && (
                <button
                  data-live-action="download-optimizer"
                  type="button"
                  onClick={() => void downloadOptimizationResult(message.optimizerJob?.jobId ?? '')}
                  disabled={downloadingOptimizationId !== null}
                  className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-gray-400"
                >
                  <FiDownload aria-hidden="true" className="h-4 w-4" />
                  {downloadingOptimizationId === message.optimizerJob.jobId ? 'Downloading...' : 'Download result'}
                </button>
              )}
              {message.downloadId && (
                <div data-live-action="generated-files" className="mt-3 flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => void downloadGeneratedFiles(message.downloadId!)}
                    disabled={removingDownloadId === message.downloadId}
                    className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50">
                    Download files (ZIP)
                  </button>
                  <button type="button" onClick={() => void removeGeneratedFiles(message.downloadId!)}
                    disabled={removingDownloadId !== null || conversationUnavailable}
                    title="Remove this ZIP from the chat to free session storage."
                    className="rounded-lg px-3 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50">
                    {removingDownloadId === message.downloadId ? 'Removing...' : 'Remove ZIP'}
                  </button>
                </div>
              )}
              {showCosts && message.costSummary && <CostDetails summary={message.costSummary} calls={message.providerCalls ?? []}
                running={message.status === 'pending'} />}
              {showModels && message.modelSelection && <div className="model-selection">
                {message.modelSelection.model} · {message.modelSelection.reasoning === 'default' ? 'Default reasoning' : message.modelSelection.reasoning}
              </div>}
              {timestamp !== undefined && (
                <time
                  dateTime={new Date(timestamp).toISOString()}
                  title={new Date(timestamp).toLocaleString()}
                  className="message-time"
                >
                  {formatResponseTime(timestamp)}
                  {message.responseStartedAt !== undefined && message.responseCompletedAt !== undefined && (
                    <> · {formatResponseDuration(message.responseStartedAt, message.responseCompletedAt)}</>
                  )}
                </time>
              )}
              {message.role === 'assistant' && message.status === 'stopped' && (
                <p className="stopped">Stopped before completion.</p>
              )}
              {message.truncated && <p className="truncated">
                A response reached the output token limit. Tool calls in that response were not executed.
              </p>}
              {message.status === 'failed' && message.failureReason && !message.activity?.some(entry => (
                entry.kind === 'response' && entry.text === message.failureReason
              )) && (
                <p className="failure-reason">{message.failureReason}</p>
              )}
              {message.role === 'assistant' && message.status === 'failed' && !conversationUnavailable && (
                <p className="failure">
                  {message.unsentFiles
                    ? `This question was not sent because its files did not finish uploading. Uploaded files stay in this chat. Attach ${message.unsentFiles.length ? message.unsentFiles.join(', ') : 'the files'} again, then send the question.`
                    : 'This response failed before completion. Send a new message to continue.'}
                </p>
              )}
            </article>
          );
        })}
        {activeSessionId !== null && sessionExpiresAt !== null && (
          <p className="pt-1 text-center text-[0.6875rem] text-gray-400">
            Chat expires at{' '}
            <time
              dateTime={new Date(sessionExpiresAt).toISOString()}
              aria-label="Chat expiration"
              className="font-medium"
            >
              {formatSessionExpiration(sessionExpiresAt)}
            </time>
            {' '}· Each new message extends the chat for another {retentionLabel(sessionRetentionSeconds)}.
          </p>
        )}
      </section>
  );
}
