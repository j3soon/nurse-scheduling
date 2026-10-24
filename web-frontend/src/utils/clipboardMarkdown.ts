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

/** Convert basic clipboard HTML without inserting it into the page. */
export function clipboardHtmlToMarkdown(html: string): string | null {
  if (!html) return null;
  const document = new DOMParser().parseFromString(html, 'text/html');
  // Keep clipboard separators, indentation, and numbering when conversion cannot preserve them.
  if (document.querySelector('table, pre, ol')) return null;
  if (Array.from(document.querySelectorAll<HTMLElement>('[style]')).some(element =>
    ['pre', 'pre-wrap', 'pre-line', 'break-spaces'].includes(element.style.whiteSpace))) return null;
  let formatted = false;
  const escape = (text: string) => text.replace(/[\\`*_[\]<>]/g, '\\$&');
  const wrap = (text: string, marker: string) => text.replace(/^(\s*)([\s\S]*?\S)(\s*)$/, `$1${marker}$2${marker}$3`);

  function render(node: Node, bold = false, italic = false): string {
    if (node.nodeType === Node.TEXT_NODE) return escape((node.textContent ?? '').replace(/\s+/g, ' '));
    if (!(node instanceof HTMLElement)) return '';
    const tag = node.tagName.toLowerCase();
    if (['script', 'style', 'template', 'noscript'].includes(tag)) return '';
    if (tag === 'br') return '\n';
    const weight = node.style.fontWeight;
    const isBold = weight ? weight === 'bold' || Number(weight) >= 600 : tag === 'b' || tag === 'strong';
    const isItalic = node.style.fontStyle ? node.style.fontStyle === 'italic' : tag === 'i' || tag === 'em';
    let text = Array.from(node.childNodes, child => render(child, bold || isBold, italic || isItalic)).join('');
    if (isBold && !bold && text.trim()) { text = wrap(text, '**'); formatted = true; }
    if (isItalic && !italic && text.trim()) { text = wrap(text, '*'); formatted = true; }
    if (tag === 'a' && text.trim()) {
      try {
        const url = new URL(node.getAttribute('href') ?? '');
        if (['http:', 'https:', 'mailto:'].includes(url.protocol)) {
          const destination = url.href.replace(/[()\\]/g, character => `%${character.charCodeAt(0).toString(16)}`);
          text = `[${text.trim()}](${destination})`;
          formatted = true;
        }
      } catch { /* A link without an absolute URL keeps its label. */ }
    }
    if (['p', 'div', 'section', 'article', 'ul', 'ol'].includes(tag)) return `\n\n${text.trim()}\n\n`;
    if (tag === 'li') return `\n- ${text.trim()}\n`;
    return text;
  }

  const markdown = render(document.body).replace(/ *\n */g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  return formatted && markdown ? markdown : null;
}
