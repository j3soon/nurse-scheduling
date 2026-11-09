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

import { translator, type Translator } from '@/i18n/messages';
import type { ActivityEntry, CompactionActivity } from './AssistantActivity';
import type { ChatMessage, ChatMessageContent } from './chatTranscript';

export type TranscriptMessage = ChatMessage & {
  presentation?: 'notice' | 'summary' | 'context';
  compaction?: CompactionActivity;
  compacted?: boolean;
};

function contextMessageCount(message: TranscriptMessage): number {
  if (message.role === 'system' || message.role === 'optimizer' || message.presentation === 'notice') return 0;
  if (message.presentation === 'summary') return message.compaction?.invalidated ? 0 : 1;
  if (message.role === 'user') return 1;
  if (message.status === 'pending') return 0;
  const activity = message.activity ?? [];
  if (activity.length === 0) {
    return message.status === 'failed' || message.status === 'stopped' || !message.content ? 0 : 1;
  }
  let count = 0;
  let step: 'none' | 'text' | 'tools' = 'none';
  for (const entry of activity) {
    if (entry.kind === 'reasoning' || entry.kind === 'response') {
      if (entry.context === 'omitted'
        || ((message.status === 'failed' || message.status === 'stopped') && entry.context !== 'complete')) {
        step = 'none';
        continue;
      }
      if (step !== 'text') {
        count += 1;
        step = 'text';
      }
    } else if (entry.kind === 'tool' && entry.state !== 'preparing') {
      if (step === 'none') count += 1;
      count += 1;
      step = entry.endsRound ? 'none' : 'tools';
    }
  }
  return count;
}

export function transcriptConversation(messages: ChatMessage[]): TranscriptMessage[] {
  const bubbles: TranscriptMessage[] = [];
  const counts: number[] = [];
  for (const message of messages) {
    const parts = transcriptMessages(message);
    const partCounts = parts.map(contextMessageCount);
    if (message.role === 'assistant' && (message.status === 'failed' || message.status === 'stopped')
      && partCounts.every(count => count === 0)
      && !message.activity?.some(entry => entry.kind === 'compaction' && entry.reason === 'manual')) {
      for (let i = bubbles.length - 1; i >= 0; i -= 1) {
        if (bubbles[i].role === 'assistant') break;
        if (bubbles[i].role === 'user' && bubbles[i].source === 'status') counts[i] = 0;
        else if (bubbles[i].role === 'user' && (bubbles[i].source === undefined || bubbles[i].source === 'optimizer')) {
          counts[i] = 0;
          break;
        }
      }
    }
    bubbles.push(...parts);
    counts.push(...partCounts);
  }
  let active = new Set<number>();
  bubbles.forEach((bubble, index) => {
    if (bubble.presentation === 'summary' && !bubble.compaction?.invalidated) {
      let keep = bubble.compaction?.keepMessages ?? 0;
      const retained = new Set<number>();
      // Keep the newest messages. The new summary replaces the earlier one, so it never counts as kept.
      for (const prior of Array.from(active).sort((a, b) => b - a)) {
        if (keep <= 0) break;
        if (counts[prior] > 0 && bubbles[prior].presentation !== 'summary') {
          retained.add(prior);
          keep -= counts[prior];
        }
      }
      retained.add(index);
      active = retained;
    } else if (counts[index] > 0) {
      active.add(index);
    }
  });
  return bubbles.map((bubble, index) => (
    counts[index] > 0 && !active.has(index) ? { ...bubble, compacted: true } : bubble
  ));
}

// Derive bubbles for display. Keep saved messages and execution ownership intact.
export function transcriptMessages(message: ChatMessage): TranscriptMessage[] {
  if (message.role !== 'assistant' || !message.activity?.some(entry => (
    entry.kind === 'notice' || entry.kind === 'schedule-spec-applied' || entry.kind === 'compaction'
  ))) return [message];
  const { activity, content, createdAt, responseStartedAt, responseCompletedAt, status, failureReason,
    truncated, modelSelection, providerCalls, costSummary, downloadId, unsentFiles, ...base } = message;
  const parts: TranscriptMessage[] = [];
  const append = (entry: ActivityEntry, presentation?: 'notice') => {
    let part = parts.at(-1);
    if (!part || part.presentation !== presentation || part.role !== 'assistant') {
      part = { ...base, content: '', activity: [], presentation };
      parts.push(part);
    }
    part.activity!.push(entry);
    if (entry.kind === 'response') part.content += entry.text;
  };
  if (content && (status !== 'failed' || content !== failureReason) && !activity!.some(entry => entry.kind === 'response')) {
    append({ kind: 'response', text: content });
  }
  for (const entry of activity!) {
    if (entry.kind === 'compaction') {
      const { summary, ...progress } = entry;
      append(progress, 'notice');
      if (summary !== undefined) parts.push({ ...base, role: 'user', source: 'app', content: `[Conversation summary]\n${summary}`,
        presentation: 'summary', compaction: entry });
    } else if (entry.kind === 'notice' && entry.text.startsWith('Sent in future model context: ')) {
      parts.push({ ...base, role: 'user', source: 'app', title: 'Context notice',
        content: entry.text.slice('Sent in future model context: '.length), presentation: 'context' });
    } else append(entry, entry.kind === 'notice' || entry.kind === 'schedule-spec-applied' ? 'notice' : undefined);
  }
  if (status === 'pending' && parts.at(-1)?.presentation && !activity!.some(entry => (
    entry.kind === 'compaction' && (entry.state === 'running' || entry.reason === 'manual')
  ))) parts.push({ ...base, content: '' });
  else if ((status === 'failed' || status === 'stopped')
    && !parts.some(part => part.role === 'assistant' && !part.presentation)
    && !activity!.some(entry => entry.kind === 'compaction' && entry.reason === 'manual')) {
    const contextIndex = parts.findIndex(part => part.presentation === 'context');
    parts.splice(contextIndex >= 0 ? contextIndex : parts.length, 0, { ...base, content: '' });
  }
  const footer = parts.findLast(part => part.role === 'assistant' && part.presentation !== 'notice')
    ?? parts.findLast(part => part.role === 'assistant') ?? parts.at(-1)!;
  Object.assign(footer, { createdAt, responseStartedAt, responseCompletedAt, status, failureReason,
    truncated, modelSelection, providerCalls, costSummary, downloadId, unsentFiles });
  return parts;
}

export function formatCharacterCount(characters: number): string {
  return characters.toLocaleString('en-US');
}

export function characterCount(text: string): number {
  return Array.from(text).length;
}

export function formatResponseDuration(startedAt: number, completedAt: number): string {
  const seconds = Math.max(0, completedAt - startedAt) / 1000;
  if (seconds < 1) return '<1s';
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  const totalSeconds = Math.round(seconds);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`;
}

export function activitySummary(entry: Exclude<ActivityEntry, { kind: 'response' }>, t: Translator = translator('en')): string {
  if (entry.kind === 'notice') return t("App notice");
  if (entry.kind === 'compaction' && entry.invalidated) return t("Conversation summary discarded");
  if (entry.kind === 'compaction') return ({
    running: t("Summarizing conversation"), completed: t("Conversation summarized"),
    failed: t("Summarization failed"), interrupted: t("Summarization interrupted"),
    skipped: t("No compaction needed"),
  }[entry.state]) + (entry.characters === undefined ? ''
    : t("{value0} · {value1} characters", { value0: (entry.step ?? 1) > 1 ? ` · pass ${entry.step}` : '', value1: formatCharacterCount(entry.characters) }));
  if (entry.kind === 'reasoning') return t("Reasoning · {value0} characters", { value0: formatCharacterCount(characterCount(entry.text)) });
  if (entry.kind === 'schedule-spec-change') return t("Schedule Spec edit");
  if (entry.kind === 'schedule-spec-check') return entry.ok ? t("Schedule Spec check passed") : t("Schedule Spec check failed");
  if (entry.kind === 'schedule-spec-applied') return entry.browserApplied === false ? t("Saved in this chat") : t("Applied to your Schedule Spec");
  if (entry.argumentsCharacters !== undefined) {
    const label = entry.state === 'preparing' ? t("Preparing tool calls") : t("{value0} · {value1}", { value0: entry.name, value1: entry.state });
    return t("{value0} · {value1} characters", { value0: label, value1: formatCharacterCount(entry.argumentsCharacters) });
  }
  if (entry.state === 'running') return t("{value0} · running", { value0: entry.name });
  if (entry.state === 'interrupted') return t("{value0} · interrupted", { value0: entry.name });
  return entry.ok ? entry.name : t("{value0} · failed", { value0: entry.name });
}

export function scheduleSpecChangeLines(beforeText: string, afterText: string): { removed: string[]; added: string[] } {
  const before = beforeText.split('\n');
  const after = afterText.split('\n');
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < before.length - prefix
    && suffix < after.length - prefix
    && before[before.length - suffix - 1] === after[after.length - suffix - 1]
  ) suffix += 1;
  return {
    removed: before.slice(prefix, before.length - suffix),
    added: after.slice(prefix, after.length - suffix),
  };
}
export function retentionLabel(seconds: number, t: Translator = translator('en')): string {
  if (seconds % 86400 === 0) {
    const days = seconds / 86400;
    return t("{value0} {value1}", { value0: days, value1: t(days === 1 ? 'day' : 'days') });
  }
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return t("{value0} {value1}", { value0: hours, value1: t(hours === 1 ? 'hour' : 'hours') });
  }
  return t("{value0} seconds", { value0: seconds.toLocaleString() });
}

export function formatSessionExpiration(timestamp: number, locale?: string): string {
  return new Date(timestamp).toLocaleString(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  });
}

export function formatResponseTime(timestamp: number, locale?: string): string {
  const completed = new Date(timestamp);
  const now = new Date();
  const sameDate = completed.getFullYear() === now.getFullYear()
    && completed.getMonth() === now.getMonth()
    && completed.getDate() === now.getDate();
  return completed.toLocaleString(locale, sameDate
    ? { hour: 'numeric', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function uploadedFileLines(files: { filename: string; bytes: number }[]): string[] {
  return files.map(file => `${file.filename} (${(file.bytes / 1000).toLocaleString('en-US')} KB)`);
}

export function messageUploadedFileLines(message: ChatMessageContent): string[] {
  if (message.source !== 'app' || message.title !== 'Files Uploaded') return [];
  const separator = message.content.indexOf(': ');
  if (separator < 0) return [];
  try {
    const files: unknown = JSON.parse(message.content.slice(separator + 2));
    if (!Array.isArray(files) || !files.every(file => file !== null && typeof file === 'object'
      && typeof file.filename === 'string' && typeof file.bytes === 'number' && Number.isFinite(file.bytes) && file.bytes >= 0)) {
      return [];
    }
    return uploadedFileLines(files);
  } catch {
    return [];
  }
}

export function messageLabel(message: ChatMessageContent, t: Translator = translator('en')): string {
  if (message.role === 'system') return t("System");
  if (message.role === 'assistant') return t("Assistant");
  if (message.role === 'optimizer') return t("Optimizer");
  const topic = message.title ? t(" - {value0}", { value0: t(message.title) }) : '';
  if (message.source === 'app') return t("User · App{value0}", { value0: topic });
  if (message.source === 'status') return t("User · Status{value0}", { value0: topic });
  if (message.source === 'optimizer') return t("User · Optimizer");
  return t("User");
}
