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

import {
  mockCreateSession,
  mockGetUploads,
  mockRemoveUpload,
  mockDownloadGeneratedZip,
  mockRemoveGeneratedZip,
  mockUploadFiles,
  mockUploadFile,
  mockGetChatExportUrl,
  mockGetCapabilities,
  mockGetSessionStatus,
  mockRunEvents,
  mockSendMessage,
  mockStreamSessionEvents,
  mockStopSession,
  mockUpdateSessionSchedule,
  mockLoadFromYaml,
  MockAiHttpError,
  defaultCapabilities,
  seedRecentChat,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import { I18nProvider } from '@/i18n/I18nProvider';
import { LOCALE_STORAGE_KEY } from '@/i18n/messages';
import { chatKey, readChatHistory } from './chatHistory';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('selects a recent chat without uploading or replacing browser Schedule Spec, then syncs on send', async () => {
    const chat = seedRecentChat();
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const history = screen.getByRole('complementary', { name: 'Recent chats' });
    await user.click(await within(history).findByRole('button', { name: /^Review older-session/ }));
    await waitFor(() => expect(mockGetSessionStatus).toHaveBeenCalledWith('older-session', null, '/ai'));
    expect(await screen.findByText('An earlier answer.')).toBeInTheDocument();
    expect(mockUpdateSessionSchedule).not.toHaveBeenCalled();
    expect(mockCreateSession).not.toHaveBeenCalled();
    expect(mockLoadFromYaml).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Schedule Spec status')).toHaveTextContent('differs');
    await waitFor(() => expect(readChatHistory()[0].conversation.preserveBrowserScheduleSpec).toBe(true));
    expect(readChatHistory()[0].lastActivityAt).toBe(chat.lastActivityAt);
    const stream = mockStreamSessionEvents.mock.calls.at(-1)?.[1] as SessionStreamOptions;
    act(() => {
      stream.onEvent({ type: 'run_context', runId: 'away-run' });
      stream.onEvent({ type: 'schedule_spec_applied', applied: { runId: 'away-run', scheduleSpecYaml: 'description: changed while away\n', diff: 'Changed while away', replacedQueuedScheduleSpec: false } });
      stream.onEvent({ type: 'done', runId: 'away-run' });
    });
    expect(mockLoadFromYaml).not.toHaveBeenCalled();
    expect(await screen.findByText(/Browser Schedule Spec was kept unchanged/)).toBeInTheDocument();
    expect(screen.getByText('Saved in this chat')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Continue with my schedule');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(mockUpdateSessionSchedule).toHaveBeenCalledWith('older-session', 'description: current Schedule Spec\n', null, '/ai');
    expect(mockUpdateSessionSchedule.mock.invocationCallOrder[0]).toBeLessThan(mockSendMessage.mock.invocationCallOrder[0]);
    expect(screen.getByLabelText('Schedule Spec status')).toHaveTextContent('matches');
    expect(chatKey(chat)).toBe('/ai\nolder-session');
  });

  it('keeps uploads pending across language changes and translates authentication errors at render', async () => {
    mockGetCapabilities.mockResolvedValue({
      ...defaultCapabilities,
      file_attachments: { ...defaultCapabilities.file_attachments, retained: true },
    });
    let rejectUploads: (error: Error) => void = () => {};
    mockGetUploads.mockImplementation(() => new Promise((_resolve, reject) => { rejectUploads = reject; }));
    const user = userEvent.setup();
    render(<I18nProvider><ExperimentalAiPage /></I18nProvider>);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Who works?');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(mockGetUploads).toHaveBeenCalled());
    const requestCount = mockGetUploads.mock.calls.length;
    const signal = mockGetUploads.mock.calls.at(-1)![3] as AbortSignal;

    localStorage.setItem(LOCALE_STORAGE_KEY, 'zh-TW');
    fireEvent(window, new StorageEvent('storage', { key: LOCALE_STORAGE_KEY }));
    expect(screen.getByRole('heading', { name: '排班 AI 對話' })).toBeInTheDocument();
    expect(mockGetUploads).toHaveBeenCalledTimes(requestCount);
    expect(signal.aborted).toBe(false);

    await act(async () => { rejectUploads(new MockAiHttpError('Invalid credentials', 401)); });
    expect(await screen.findByRole('alert')).toHaveTextContent('AI 驗證憑證遭拒。請輸入目前的 AI 權杖後重試。');
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en');
    fireEvent(window, new StorageEvent('storage', { key: LOCALE_STORAGE_KEY }));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'AI credentials were rejected. Enter the current AI token and try again.',
    );
    localStorage.removeItem(LOCALE_STORAGE_KEY);
  });

  it('lists uploads before the assistant responds and removes an unused file', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, file_attachments: { ...defaultCapabilities.file_attachments, retained: true } });
    mockRemoveUpload.mockImplementation(async () => { mockGetUploads.mockResolvedValue([]); });
    mockGetUploads.mockResolvedValue([{ id: 'upload-1', filename: 'ward.xlsx', media_type: 'application/xlsx', bytes: 5000 }]);
    let finishResponse: () => void = () => {};
    // The run stays active after the backend accepts the message.
    mockRunEvents.mockImplementation(() => new Promise<void>(resolve => { finishResponse = resolve; }));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.upload(await screen.findByLabelText('Attach files'), new File(['workbook'], 'ward.xlsx'));
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Read the workbook');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    const panel = await screen.findByRole('complementary', { name: 'Session files' });
    expect(await within(panel).findByText('ward.xlsx')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Remove ward.xlsx' })).toBeDisabled();
    await act(async () => { finishResponse(); });
    await user.click(within(panel).getByRole('button', { name: 'Remove ward.xlsx' }));
    await waitFor(() => expect(mockRemoveUpload).toHaveBeenCalledWith('session-id', 'upload-1', null, '/ai'));
    expect(await within(panel).findByText('No uploaded files.')).toBeInTheDocument();
  });

  it('downloads server-captured files from an assistant answer', async () => {
    mockRunEvents.mockImplementation(async (_id: string, _question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'download', downloadId: 'zip-run' });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Make a downloadable CSV');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:generated-zip');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    await user.click(await screen.findByRole('button', { name: 'Download files (ZIP)' }));
    await waitFor(() => expect(mockDownloadGeneratedZip).toHaveBeenCalledWith('session-id', 'zip-run', null, '/ai'));
    expect(click).toHaveBeenCalled();
  });

  it.each([false, true])('removes a generated ZIP only after the server accepts deletion (failure: %s)', async failure => {
    mockRunEvents.mockImplementation(async (_id: string, _question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'delta', text: 'Your CSV is ready.' });
      callbacks.onEvent({ type: 'download', downloadId: 'zip-run' });
    });
    let finishRemoval!: () => void;
    mockRemoveGeneratedZip.mockImplementation(() => new Promise<void>((resolve, reject) => {
      finishRemoval = () => failure ? reject(new Error('Removal failed.')) : resolve();
    }));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Make a CSV');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await user.click(await screen.findByRole('button', { name: 'Remove ZIP' }));
    expect(mockRemoveGeneratedZip).toHaveBeenCalledWith('session-id', 'zip-run', null, '/ai');
    expect(screen.getByRole('button', { name: 'Removing...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Download files (ZIP)' })).toBeDisabled();
    await act(async () => { finishRemoval(); });
    if (failure) {
      expect(await screen.findByRole('alert')).toHaveTextContent('Removal failed.');
      expect(screen.getByRole('button', { name: 'Download files (ZIP)' })).toBeEnabled();
      expect(screen.getByRole('button', { name: 'Remove ZIP' })).toBeEnabled();
    } else {
      expect(screen.queryByRole('button', { name: 'Download files (ZIP)' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Remove ZIP' })).not.toBeInTheDocument();
    }
    expect(screen.getByText('Your CSV is ready.')).toBeInTheDocument();
  });

  it('shows a download warning without offering to retry a completed answer', async () => {
    mockRunEvents.mockImplementation(async (_id: string, _question: string, callbacks: SessionStreamOptions) => {
      callbacks.onEvent({ type: 'delta', text: 'Your files are ready.' });
      callbacks.onEvent({ type: 'warning', message: 'The generated ZIP could not be retained.' });
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Make a CSV');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('The generated ZIP could not be retained.');
    expect(screen.getByText('Your files are ready.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('downloads the prepared server archive in a hidden frame without a popup or Blob', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, saved_chat_export: true });
    const user = userEvent.setup();
    const blob = vi.spyOn(URL, 'createObjectURL');
    const open = vi.spyOn(window, 'open');
    let finishPreparation!: (url: string) => void;
    mockGetChatExportUrl.mockReturnValue(new Promise<string>(resolve => { finishPreparation = resolve; }));
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await user.click(screen.getByRole('button', { name: 'Export Chat', exact: true }));
    expect(screen.getByRole('button', { name: 'Preparing export…' })).toBeDisabled();
    expect(document.querySelector('iframe')).toBeNull();
    expect(mockGetChatExportUrl).toHaveBeenCalledWith('session-id', null, '/ai');
    finishPreparation('/ai/v1/sessions/session-id/export?download=prepared&token=temporary');
    await waitFor(() => expect(document.querySelector('iframe')).not.toBeNull());
    const frame = document.querySelector('iframe')!;
    expect(frame.hidden).toBe(true);
    await waitFor(() => expect(frame.src).toContain('/export?download=prepared&token=temporary'));
    expect(open).not.toHaveBeenCalled();
    expect(blob).not.toHaveBeenCalled();
    expect(screen.getByText('Chat download requested. Check your browser’s downloads.')).toBeVisible();
    // A server error loads a document instead of starting an attachment download.
    fireEvent.load(frame);
    expect(screen.getByText('The chat download could not start. Please try Export Chat again.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Export Chat', exact: true })).toBeEnabled();
  });

  it('reports archive preparation errors inline without opening a download frame', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, saved_chat_export: true });
    mockGetChatExportUrl.mockRejectedValue(new Error('The chat archive could not be created. Try again.'));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await user.click(screen.getByRole('button', { name: 'Export Chat', exact: true }));
    expect(screen.getByText('The chat archive could not be created. Try again.')).toBeVisible();
    expect(document.querySelector('iframe')).toBeNull();
    expect(screen.getByRole('button', { name: 'Export Chat', exact: true })).toBeEnabled();
  });

  it('disables chat export when the server has no saved history', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Question');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByRole('button', { name: 'Export Chat', exact: true })).toBeDisabled();
    expect(mockGetChatExportUrl).not.toHaveBeenCalled();
  });

  it('asks for files again instead of recovering a request whose upload never finished', async () => {
    const pendingRequest = {
      messageId: 'original-request', question: 'Read these files', questionId: 'question', assistantId: 'answer',
      createdAt: Date.now() - 1000, uploading: true, pendingFiles: ['second.xlsx'],
    };
    window.sessionStorage.setItem('nurse-scheduling-ai-conversation', JSON.stringify({
      sessionId: 'restored-session', endpoint: '/ai', expiresAt: Date.now() + 60_000, retentionSeconds: 2592000,
      messages: [
        { id: 'question', role: 'user', content: pendingRequest.question },
        { id: 'answer', role: 'assistant', content: '', status: 'pending' },
      ],
      syncedScheduleSpec: 'description: original schedule\n', pendingRequest,
    }));
    render(<ExperimentalAiPage />);

    expect(await screen.findByText('This question was not sent because its files did not finish uploading. Uploaded files stay in this chat. Attach second.xlsx again, then send the question.'))
      .toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    expect(mockSendMessage).not.toHaveBeenCalled();
    await waitFor(() => {
      const stored = JSON.parse(window.sessionStorage.getItem('nurse-scheduling-ai-conversation') ?? '{}');
      expect(stored.pendingRequest).toBeNull();
    });
  });

  it('does not submit a question stopped during upload', async () => {
    let finishUpload: () => void = () => {};
    mockUploadFiles.mockImplementation((_sessionId: string, files: File[]) => new Promise(resolve => {
      finishUpload = () => resolve(files.map((file, index) => ({
        id: `upload-${index + 1}`, filename: file.name, media_type: 'text/csv', bytes: file.size,
      })));
    }));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.upload(await screen.findByLabelText('Attach files'), new File(['a,b'], 'ward.csv', { type: 'text/csv' }));
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Read the file');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(mockUploadFiles).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    await act(async () => finishUpload());

    // The named Stop also covers a question that reaches the server later.
    expect(mockStopSession).toHaveBeenCalledWith('session-id', null, '/ai', expect.any(String));
    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(await screen.findByText('Stopped before completion.')).toBeInTheDocument();
  });

  it('previews and sends image files', async () => {
    mockGetCapabilities.mockResolvedValueOnce(defaultCapabilities);
    const createObjectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:image-preview');
    const revokeObjectUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const user = userEvent.setup();
    const image = new File(['png'], 'ward.png', { type: 'image/png' });
    render(<ExperimentalAiPage />);

    const input = await screen.findByLabelText('Attach files');
    expect(input.closest('label')?.querySelector('svg')).not.toBeNull();
    await user.upload(input, image);
    expect(screen.getByAltText('Preview of ward.png')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'What is shown?');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(mockUploadFiles).toHaveBeenCalledWith(
      'session-id',
      [image],
      null,
      '/ai',
      expect.any(AbortSignal),
    );
    expect(mockRunEvents).toHaveBeenCalledWith(
      'session-id',
      'What is shown?',
      expect.any(Object),
      expect.any(AbortSignal),
      null,
      '/ai',
    );
    expect(createObjectUrl).toHaveBeenCalledWith(image);
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:image-preview');
  });

  it('adds attachments dropped onto the message composer', async () => {
    mockGetCapabilities.mockResolvedValueOnce(defaultCapabilities);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:dropped-image');
    const image = new File(['png'], 'dropped.png', { type: 'image/png' });
    render(<ExperimentalAiPage />);

    const composer = await screen.findByRole('form', { name: 'Message composer' });
    const dataTransfer = { files: [image], types: ['Files'], dropEffect: 'none' };
    fireEvent.dragEnter(composer, { dataTransfer });
    expect(screen.getByText('Drop files to attach')).toBeInTheDocument();

    fireEvent.dragOver(composer, { dataTransfer });
    expect(dataTransfer.dropEffect).toBe('copy');
    fireEvent.drop(composer, { dataTransfer });

    expect(screen.queryByText('Drop files to attach')).not.toBeInTheDocument();
    expect(screen.getByAltText('Preview of dropped.png')).toBeInTheDocument();
  });

  it.each([
    { maxFiles: 1, totalBytes: 20 },
    { maxFiles: 32, totalBytes: 6 },
  ])('includes retained uploads in picker limits ($maxFiles files, $totalBytes bytes)', async ({ maxFiles, totalBytes }) => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, file_attachments: {
      enabled: true, retained: true, max_files: maxFiles, max_bytes_per_file: 25,
      max_bytes_per_session: totalBytes
    } });
    mockGetUploads.mockResolvedValue([{ id: 'existing', filename: 'existing.txt', media_type: 'text/plain', bytes: 4 }]);
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(await screen.findByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByRole('button', { name: 'Remove existing.txt' });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
    if (maxFiles === 1) {
      expect(screen.getByLabelText('Attach files')).toBeDisabled();
    } else {
      await user.upload(screen.getByLabelText('Attach files'), new File(['abc'], 'extra.txt'));
      expect(await screen.findByRole('alert')).toHaveTextContent('Files in this chat must total');
    }
    expect(mockUploadFiles).not.toHaveBeenCalled();
  });

  it('rounds the session file total in its limit message', async () => {
    mockGetCapabilities.mockResolvedValue({ ...defaultCapabilities, file_attachments: {
      enabled: true, retained: true, max_files: 32, max_bytes_per_file: 25_000_000,
      max_bytes_per_session: 123_456_789,
    } });
    mockGetUploads.mockResolvedValue([{ id: 'existing', filename: 'existing.txt', media_type: 'text/plain', bytes: 123_456_788 }]);
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(await screen.findByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByRole('button', { name: 'Remove existing.txt' });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
    await user.upload(screen.getByLabelText('Attach files'), new File(['abc'], 'extra.txt'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Files in this chat must total 123.5 MB or less.');
  });

  it('uploads files individually before submitting the question', async () => {
    mockGetCapabilities.mockResolvedValueOnce({ ...defaultCapabilities, file_attachments: {
      enabled: true, retained: true, max_files: 32, max_bytes_per_file: 25,
      max_bytes_per_session: 200,
    } });
    mockGetUploads.mockResolvedValue([{ id: 'existing', filename: 'existing.txt', media_type: 'text/plain', bytes: 3 }]);
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.type(await screen.findByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Hello');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByRole('button', { name: 'Remove existing.txt' });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument());
    mockUploadFile.mockImplementation(async (_sessionId: string, file: File, _signal: AbortSignal, _authToken: string | null,
      _endpoint: string) => {
      return [{ id: file.name, filename: file.name, media_type: 'text/plain', bytes: file.size }];
    });
    const files = ['one.txt', 'two.txt', 'three.txt'].map(name => new File(['abc'], name));
    await user.upload(screen.getByLabelText('Attach files'), files);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Read the files.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(2));
    expect(mockUploadFile.mock.calls.map(call => (call[1] as File).name)).toEqual(['one.txt', 'two.txt', 'three.txt']);
  });

  it('keeps successful uploads visible when a later upload fails', async () => {
    mockGetCapabilities.mockResolvedValueOnce({ ...defaultCapabilities, file_attachments: {
      enabled: true, retained: true, max_files: 32, max_bytes_per_file: 25,
      max_bytes_per_session: 200,
    } });
    mockGetUploads.mockResolvedValue([{ id: 'first', filename: 'one.txt', media_type: 'text/plain', bytes: 3 }]);
    mockUploadFiles.mockResolvedValueOnce([{ id: 'first', filename: 'one.txt', media_type: 'text/plain', bytes: 3 }])
      .mockRejectedValueOnce(new Error('Later batch failed.'));
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    await user.upload(await screen.findByLabelText('Attach files'), [new File(['abc'], 'one.txt'), new File(['def'], 'two.txt')]);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Read the files.');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Later batch failed.');
    expect(within(screen.getByLabelText('Session files')).getByText('one.txt')).toBeInTheDocument();
    expect(screen.getByText('This question was not sent because its files did not finish uploading. Uploaded files stay in this chat. Attach two.txt again, then send the question.'))
      .toBeInTheDocument();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('accepts and sends an arbitrary file type', async () => {
    mockGetCapabilities.mockResolvedValueOnce({
      file_attachments: {
        enabled: true,
        max_files: 2,
        max_bytes_per_file: 5_000_000,
        max_bytes_per_session: 200_000_000,
      },
    });
    const user = userEvent.setup();
    const document = new File(['custom bytes'], 'staff.custom', { type: 'application/x-custom' });
    render(<ExperimentalAiPage />);

    const input = await screen.findByLabelText('Attach files');
    expect(input).not.toHaveAttribute('accept');
    await user.upload(input, document);
    expect(screen.getByText('custom')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Check the file.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(mockUploadFiles).toHaveBeenCalledWith(
      'session-id',
      [expect.objectContaining({ name: 'staff.custom', type: 'application/x-custom' })],
      null,
      '/ai',
      expect.any(AbortSignal),
    );
    expect(mockRunEvents).toHaveBeenCalledWith(
      'session-id',
      'Check the file.',
      expect.any(Object),
      expect.any(AbortSignal),
      null,
      '/ai',
    );
  });

  it('sends PDF and XLSX files without rewriting their media types', async () => {
    mockGetCapabilities.mockResolvedValueOnce(defaultCapabilities);
    const user = userEvent.setup();
    const pdf = new File(['pdf'], 'notes.pdf', { type: '' });
    const workbook = new File(['xlsx'], 'coverage.xlsx', { type: '' });
    render(<ExperimentalAiPage />);

    const input = await screen.findByLabelText('Attach files');
    await user.upload(input, [pdf, workbook]);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Read both files.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(mockUploadFiles).toHaveBeenNthCalledWith(
      1, 'session-id', [expect.objectContaining({ name: 'notes.pdf', type: '' })],
      null, '/ai', expect.any(AbortSignal),
    );
    expect(mockUploadFiles).toHaveBeenNthCalledWith(
      2, 'session-id', [expect.objectContaining({ name: 'coverage.xlsx', type: '' })],
      null, '/ai', expect.any(AbortSignal),
    );
    expect(mockRunEvents).toHaveBeenCalledWith(
      'session-id',
      'Read both files.',
      expect.any(Object),
      expect.any(AbortSignal),
      null,
      '/ai',
    );
  });

  it('asks for files again when the question was not sent', async () => {
    mockGetCapabilities.mockResolvedValueOnce(defaultCapabilities);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:image-preview');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    // Only an upload that did not finish requires the files again.
    mockUploadFiles.mockRejectedValueOnce(new Error('The upload connection failed.'));
    const user = userEvent.setup();
    const image = new File(['png'], 'ward.png', { type: 'image/png' });
    render(<ExperimentalAiPage />);

    await user.upload(await screen.findByLabelText('Attach files'), image);
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Check this image.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('This question was not sent because its files did not finish uploading. Uploaded files stay in this chat. Attach ward.png again, then send the question.'))
      .toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    expect(mockRunEvents).not.toHaveBeenCalled();
  });

  it('asks for a new message, not the files, when a run fails after its uploads', async () => {
    // The upload succeeds, then the run fails.
    mockRunEvents.mockImplementationOnce(async () => {
      throw new Error('The temporary AI sandbox failed.');
    });
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);

    await user.upload(await screen.findByLabelText('Attach files'), new File(['png'], 'ward.png', { type: 'image/png' }));
    await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Check this image.');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('This response failed before completion. Send a new message to continue.')).toBeInTheDocument();
    expect(screen.queryByText(/did not finish uploading/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });
});
