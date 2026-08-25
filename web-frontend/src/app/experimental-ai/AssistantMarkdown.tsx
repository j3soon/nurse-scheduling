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
    <div className="relative mb-2 max-w-full last:mb-0">
      <button
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
        className="max-w-full overflow-x-auto rounded-lg bg-gray-900 py-3 pl-3 pr-12 text-sm text-gray-100 [&_code]:bg-transparent [&_code]:p-0"
      >
        {children}
      </pre>
    </div>
  );
}

const components: Components = {
  h1: ({ children }) => <h1 className="mb-2 mt-4 text-xl font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1.5 mt-3 font-semibold first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h4>,
  h5: ({ children }) => <h5 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h5>,
  h6: ({ children }) => <h6 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h6>,
  p: ({ children }) => <p className="mb-2 whitespace-pre-wrap last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 ml-5 list-disc space-y-1 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 ml-5 list-decimal space-y-1 last:mb-0">{children}</ol>,
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-4 border-gray-300 pl-3 text-gray-600 last:mb-0">
      {children}
    </blockquote>
  ),
  a: ({ children, href }) => {
    const external = href?.startsWith('http://') || href?.startsWith('https://');
    return (
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        className="font-medium text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
      >
        {children}
      </a>
    );
  },
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: ({ children, className }) => (
    <code className={`rounded bg-gray-100 px-1 py-0.5 font-mono text-[0.9em] ${className ?? ''}`}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="mb-2 max-w-full overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-gray-300 bg-gray-100 px-2 py-1.5 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-gray-300 px-2 py-1.5 align-top">{children}</td>,
  hr: () => <hr className="my-3 border-gray-300" />,
  img: ({ alt }) => (
    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-sm text-gray-600">
      [Remote image omitted{alt ? `: ${alt}` : ''}]
    </span>
  ),
};

export default function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="break-words leading-6">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {content}
      </Markdown>
    </div>
  );
}
