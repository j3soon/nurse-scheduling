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
  mockRunEvents,
  mockSendMessage,
  setupExperimentalAiPageTests,
} from '@/test/experimentalAiPage';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExperimentalAiPage from './page';
import type { SessionStreamOptions } from './sessionEvents';

describe('ExperimentalAiPage', () => {
  setupExperimentalAiPageTests();

  it('pastes Markdown over the selection and submits the converted message', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const input = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }) as HTMLTextAreaElement;
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, 'Keep old ending');
    input.setSelectionRange(5, 8);
    fireEvent.paste(input, { clipboardData: { getData: (type: string) => type === 'text/html' ? '<b>new</b> <a href="https://example.com">link</a>' : 'new link' } });
    expect(input).toHaveValue('Keep **new** [link](https://example.com/) ending');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(mockSendMessage.mock.calls[0][1]).toBe('Keep **new** [link](https://example.com/) ending');
  });

  it('submits long messages without a character limit', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const input = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }) as HTMLTextAreaElement;
    await waitFor(() => expect(input).toBeEnabled());
    expect(input).not.toHaveAttribute('maxlength');
    input.focus();
    await user.paste('x'.repeat(300000));
    expect(input.value).toHaveLength(300000);
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(mockSendMessage.mock.calls[0][1]).toHaveLength(300000);
  });

  it('keeps complete formatted and plain text pastes', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const input = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }) as HTMLTextAreaElement;
    await waitFor(() => expect(input).toBeEnabled());
    input.focus();
    await user.paste('Literal **Markdown**');
    expect(input).toHaveValue('Literal **Markdown**');
    fireEvent.change(input, { target: { value: 'x'.repeat(7998) } });
    input.setSelectionRange(7998, 7998);
    fireEvent.paste(input, { clipboardData: { getData: () => '<b>long paste</b>' } });
    expect(input.value).toBe('x'.repeat(7998) + '**long paste**');
  });

  it('starts with a single-line composer and grows with the draft', async () => {
    const user = userEvent.setup();
    render(<ExperimentalAiPage />);
    const composer = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });

    expect(composer).toHaveAttribute('rows', '1');
    expect(composer).toHaveStyle({ height: '24px', overflowY: 'hidden' });
    Object.defineProperty(composer, 'scrollHeight', { configurable: true, value: 96 });
    await user.type(composer, 'A longer question that wraps onto another line.');

    expect(composer).toHaveStyle({ height: '96px', overflowY: 'hidden' });
  });

  it('adds browser speech recognition results to the message draft', async () => {
    const recognition: {
      onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
      onend: (() => void) | null;
      onerror: ((event: { error?: string }) => void) | null;
      continuous: boolean;
      interimResults: boolean;
      lang: string;
      processLocally: boolean;
      start: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
    } = {
      continuous: false,
      interimResults: false,
      lang: '',
      processLocally: false,
      onresult: null,
      onend: null,
      onerror: null,
      start: vi.fn(),
      stop: vi.fn(),
    };
    function MockSpeechRecognition() {
      return recognition;
    }
    Object.defineProperty(window, 'SpeechRecognition', {
      configurable: true,
      value: MockSpeechRecognition,
    });
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (X11; Linux x86_64; rv:158.0) Gecko/20100101 Firefox/158.0',
    );
    const user = userEvent.setup();

    try {
      render(<ExperimentalAiPage />);
      const draft = screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' });
      await user.type(draft, 'Please');
      const languageSelect = await screen.findByRole('combobox', { name: 'Dictation language' });
      expect(languageSelect).toHaveValue('');
      await user.selectOptions(languageSelect, 'zh-TW');
      await user.click(await screen.findByRole('button', { name: 'Start dictation' }));

      expect(recognition.start).toHaveBeenCalledOnce();
      expect(recognition.lang).toBe('zh-TW');
      expect(recognition.processLocally).toBe(true);
      expect(languageSelect).toBeDisabled();
      act(() => recognition.onresult?.({ results: [[{ transcript: 'add a night shift' }]] }));

      expect(draft).toHaveValue('Please add a night shift');
      // Continuous recognition reports one entry per utterance, so segments need a separator.
      act(() => recognition.onresult?.({
        results: [[{ transcript: 'add a night shift' }], [{ transcript: 'for P1' }]],
      }));

      expect(draft).toHaveValue('Please add a night shift for P1');
      act(() => recognition.onresult?.({
        results: [[{ transcript: ' add a night shift ' }], [{ transcript: ' for P1' }]],
      }));

      expect(draft).toHaveValue('Please add a night shift for P1');
      await user.click(screen.getByRole('button', { name: 'Stop dictation' }));
      expect(recognition.stop).toHaveBeenCalledOnce();
      act(() => recognition.onend?.());
      expect(languageSelect).toBeEnabled();
      expect(screen.getByRole('button', { name: 'Start dictation' })).toHaveAttribute('aria-pressed', 'false');
    } finally {
      delete window.SpeechRecognition;
    }
  });

  it('reports a real dictation fault but stays quiet when nobody spoke', async () => {
    const recognition = {
      continuous: false,
      interimResults: false,
      lang: '',
      onresult: null,
      onend: null as (() => void) | null,
      onerror: null as ((event: { error?: string }) => void) | null,
      start: vi.fn(),
      stop: vi.fn(),
    };
    Object.defineProperty(window, 'SpeechRecognition', {
      configurable: true,
      value: function MockSpeechRecognition() {
        return recognition;
      },
    });
    const user = userEvent.setup();

    try {
      render(<ExperimentalAiPage />);
      await user.click(await screen.findByRole('button', { name: 'Start dictation' }));

      // Silence and a deliberate stop both arrive as errors, so neither may alarm the user.
      act(() => recognition.onerror?.({ error: 'no-speech' }));
      expect(screen.queryByText(/Speech recognition stopped/)).not.toBeInTheDocument();
      act(() => recognition.onerror?.({ error: 'aborted' }));
      expect(screen.queryByText(/Speech recognition stopped/)).not.toBeInTheDocument();

      await user.click(await screen.findByRole('button', { name: 'Start dictation' }));
      act(() => recognition.onerror?.({ error: 'audio-capture' }));
      expect(await screen.findByText(/Speech recognition stopped/)).toBeInTheDocument();
    } finally {
      delete window.SpeechRecognition;
    }
  });

  it('does not offer the legacy speech recognition implementation in Firefox', async () => {
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0',
    );
    Object.defineProperty(window, 'SpeechRecognition', {
      configurable: true,
      value: vi.fn(),
    });

    try {
      render(<ExperimentalAiPage />);

      const compatibilityLink = await screen.findByRole('link', { name: 'Firefox dictation compatibility' });
      expect(compatibilityLink).toHaveAttribute('href', 'https://www.firefox.com/channel/desktop/#nightly');
      expect(screen.getByText(/Dictation is unavailable in this Firefox version/)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Start dictation' })).not.toBeInTheDocument();
    } finally {
      delete window.SpeechRecognition;
    }
  });

  it('shows current setup guidance in Firefox builds with on-device recognition', async () => {
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (X11; Linux x86_64; rv:158.0) Gecko/20100101 Firefox/158.0',
    );

    render(<ExperimentalAiPage />);

    const setupLink = await screen.findByRole('link', { name: 'Enable experimental dictation in Firefox' });
    expect(setupLink).toHaveAttribute('href', 'https://bugzilla.mozilla.org/show_bug.cgi?id=1940906');
    expect(screen.getByText(/enable media\.webspeech\.recognition\.enable, then reload/)).toBeInTheDocument();
  });

  it('ignores non-user scroll events while following streamed text', async () => {
    const user = userEvent.setup();
    let sendDelta: ((text: string) => void) | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      sendDelta = text => callbacks.onEvent({ type: 'delta', text });
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    const scrollTo = vi.mocked(window.scrollTo);
    scrollTo.mockClear();
    let scrollYPosition = 100;
    const scrollHeight = vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(900);
    const innerHeight = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(800);
    const scrollY = vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => scrollYPosition);

    try {
      render(<ExperimentalAiPage />);
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Stream details.');
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await waitFor(() => expect(sendDelta).toBeDefined());
      await waitFor(() => expect(scrollTo).toHaveBeenCalled());

      scrollYPosition = 99;
      act(() => {
        window.dispatchEvent(new Event('scroll'));
      });
      const callsBeforeDelta = scrollTo.mock.calls.length;
      act(() => sendDelta?.('More streamed content.'));

      await waitFor(() => expect(screen.getByText('More streamed content.')).toBeInTheDocument());
      expect(scrollTo.mock.calls.length).toBeGreaterThan(callsBeforeDelta);
      expect(screen.queryByRole('button', { name: 'Scroll to bottom' })).not.toBeInTheDocument();
      await act(async () => finishStream?.());
    } finally {
      scrollHeight.mockRestore();
      innerHeight.mockRestore();
      scrollY.mockRestore();
    }
  });

  it('stops following streamed text after a user scrolls above the bottom', async () => {
    const user = userEvent.setup();
    let sendDelta: ((text: string) => void) | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      sendDelta = text => callbacks.onEvent({ type: 'delta', text });
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    const scrollTo = vi.mocked(window.scrollTo);
    const scrollHeight = vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(900);
    const innerHeight = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(800);
    let scrollYPosition = 100;
    const scrollY = vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => scrollYPosition);

    try {
      render(<ExperimentalAiPage />);
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Stream details.');
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await waitFor(() => expect(sendDelta).toBeDefined());
      await waitFor(() => expect(scrollTo).toHaveBeenCalled());

      scrollYPosition = 99;
      act(() => {
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: -1 }));
        window.dispatchEvent(new Event('scroll'));
      });
      await waitFor(() => expect(screen.getByRole('button', { name: 'Scroll to bottom' })).toBeInTheDocument());
      const callsBeforeDelta = scrollTo.mock.calls.length;
      act(() => sendDelta?.('More streamed content.'));

      await waitFor(() => expect(screen.getByText('More streamed content.')).toBeInTheDocument());
      expect(scrollTo).toHaveBeenCalledTimes(callsBeforeDelta);
      await act(async () => finishStream?.());
    } finally {
      scrollHeight.mockRestore();
      innerHeight.mockRestore();
      scrollY.mockRestore();
    }
  });

  it('returns to the top and stops following streamed text until the bottom shortcut is used', async () => {
    const user = userEvent.setup();
    let sendDelta: ((text: string) => void) | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      sendDelta = text => callbacks.onEvent({ type: 'delta', text });
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    const scrollTo = vi.mocked(window.scrollTo);
    const scrollHeight = vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(1300);
    const innerHeight = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(800);
    let scrollYPosition = 500;
    const scrollY = vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => scrollYPosition);

    try {
      render(<ExperimentalAiPage />);
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Stream details.');
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await waitFor(() => expect(sendDelta).toBeDefined());
      await waitFor(() => expect(scrollTo).toHaveBeenCalled());

      act(() => window.dispatchEvent(new Event('scroll')));
      await user.click(screen.getByRole('button', { name: 'Back to top' }));
      scrollYPosition = 0;
      expect(scrollTo).toHaveBeenLastCalledWith({ top: 0, behavior: 'instant' });
      act(() => window.dispatchEvent(new Event('scroll')));
      expect(screen.queryByRole('button', { name: 'Back to top' })).not.toBeInTheDocument();
      await waitFor(() => expect(screen.getByRole('button', { name: 'Scroll to bottom' })).toBeInTheDocument());
      const callsBeforeDelta = scrollTo.mock.calls.length;
      act(() => sendDelta?.('More streamed content.'));

      await waitFor(() => expect(screen.getByText('More streamed content.')).toBeInTheDocument());
      expect(scrollTo).toHaveBeenCalledTimes(callsBeforeDelta);
      await user.click(screen.getByRole('button', { name: 'Scroll to bottom' }));
      expect(scrollTo).toHaveBeenLastCalledWith({ top: 1300, behavior: 'instant' });
      await act(async () => finishStream?.());
    } finally {
      scrollHeight.mockRestore();
      innerHeight.mockRestore();
      scrollY.mockRestore();
    }
  });

  it('resumes following streamed text when the user scrolls to the current bottom', async () => {
    const user = userEvent.setup();
    let sendDelta: ((text: string) => void) | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      sendDelta = text => callbacks.onEvent({ type: 'delta', text });
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    let pageHeight = 900;
    let scrollYPosition = 100;
    const scrollTo = vi.mocked(window.scrollTo);
    const scrollHeight = vi.spyOn(document.documentElement, 'scrollHeight', 'get')
      .mockImplementation(() => pageHeight);
    const innerHeight = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(800);
    const scrollY = vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => scrollYPosition);

    try {
      render(<ExperimentalAiPage />);
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Stream details.');
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await waitFor(() => expect(sendDelta).toBeDefined());

      scrollYPosition = 99;
      act(() => {
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: -1 }));
        window.dispatchEvent(new Event('scroll'));
      });
      await screen.findByRole('button', { name: 'Scroll to bottom' });

      scrollYPosition = 100;
      act(() => {
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: 1 }));
        window.dispatchEvent(new Event('scroll'));
      });
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Scroll to bottom' })).not.toBeInTheDocument();
      });

      const callsBeforeGrowth = scrollTo.mock.calls.length;
      pageHeight = 901;
      act(() => sendDelta?.('More streamed content.'));
      await waitFor(() => expect(scrollTo.mock.calls.length).toBeGreaterThan(callsBeforeGrowth));
      await act(async () => finishStream?.());
    } finally {
      scrollHeight.mockRestore();
      innerHeight.mockRestore();
      scrollY.mockRestore();
    }
  });

  it('uses the same follow flag for streamed tool activity', async () => {
    const user = userEvent.setup();
    let startTool: ((activity: { name: string; arguments: string }) => void) | undefined;
    let finishTool: ((activity: { name: string; arguments: string; result: string; ok: boolean }) => void) | undefined;
    let finishStream: (() => void) | undefined;
    mockRunEvents.mockImplementationOnce(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      startTool = activity => callbacks.onEvent({ type: 'tool_start', activity });
      finishTool = activity => callbacks.onEvent({ type: 'tool', activity });
      await new Promise<void>(resolve => {
        finishStream = resolve;
      });
    });
    let scrollYPosition = 100;
    const scrollTo = vi.mocked(window.scrollTo);
    const scrollHeight = vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(900);
    const innerHeight = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(800);
    const scrollY = vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => scrollYPosition);
    const tool = { name: 'bash', arguments: '{"command":"date"}' };

    try {
      render(<ExperimentalAiPage />);
      await user.type(screen.getByRole('textbox', { name: 'Ask about the current Schedule Spec' }), 'Check the schedule.');
      await user.click(screen.getByRole('button', { name: 'Send' }));
      await waitFor(() => expect(startTool).toBeDefined());

      const callsBeforeTool = scrollTo.mock.calls.length;
      act(() => startTool?.(tool));
      await waitFor(() => expect(scrollTo.mock.calls.length).toBeGreaterThan(callsBeforeTool));

      scrollYPosition = 99;
      act(() => {
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: -1 }));
        window.dispatchEvent(new Event('scroll'));
      });
      await screen.findByRole('button', { name: 'Scroll to bottom' });
      const callsBeforeResult = scrollTo.mock.calls.length;
      act(() => finishTool?.({ ...tool, result: 'exit_code: 0', ok: true }));

      await waitFor(() => expect(screen.getByText('bash')).toBeInTheDocument());
      expect(scrollTo).toHaveBeenCalledTimes(callsBeforeResult);
      await act(async () => finishStream?.());
    } finally {
      scrollHeight.mockRestore();
      innerHeight.mockRestore();
      scrollY.mockRestore();
    }
  });
});
