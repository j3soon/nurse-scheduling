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

'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { FiCheck, FiCopy } from 'react-icons/fi';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

// react-markdown escapes unsafe output by default. Keep raw HTML disabled and
// omit remote images so untrusted model output cannot load third-party content.
// https://github.com/remarkjs/react-markdown#security

function CodeBlock({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);
  const copiedResetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (copiedResetTimeoutRef.current) clearTimeout(copiedResetTimeoutRef.current);
  }, []);

  const copy = async () => {
    try {
      const code = (preRef.current?.textContent ?? '').replace(/\n$/, '');
      await navigator.clipboard.writeText(code);
      setCopied(true);
      if (copiedResetTimeoutRef.current) clearTimeout(copiedResetTimeoutRef.current);
      copiedResetTimeoutRef.current = setTimeout(() => {
        setCopied(false);
        copiedResetTimeoutRef.current = null;
      }, 2000);
    } catch (error) {
      console.error('Failed to copy code block:', error);
    }
  };

  return (
    <div className="code-container">
      <button
        data-live-action="copy-code"
        type="button"
        onClick={copy}
        aria-label={copied ? 'Copied' : 'Copy code'}
        title={copied ? 'Copied' : 'Copy code'}
        className="absolute right-2 top-2 rounded-md border border-gray-600 bg-gray-800 p-1.5 text-gray-200 hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
      >
        {copied ? <FiCheck aria-hidden="true" className="h-4 w-4" /> : <FiCopy aria-hidden="true" className="h-4 w-4" />}
      </button>
      <pre
        ref={preRef}
        className="code-block"
      >
        {children}
      </pre>
    </div>
  );
}

const components: Components = {
  a: ({ children, href }) => {
    const external = href?.startsWith('http://') || href?.startsWith('https://');
    return (
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
      >
        {children}
      </a>
    );
  },
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: ({ children, className }) => (
    <code className={className}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="table-container">
      <table>{children}</table>
    </div>
  ),
  img: ({ alt }) => (
    <span className="remote-image-omitted">
      [Remote image omitted{alt ? `: ${alt}` : ''}]
    </span>
  ),
};

export default function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="content">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {content}
      </Markdown>
    </div>
  );
}
