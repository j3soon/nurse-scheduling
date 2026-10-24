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

import { clipboardHtmlToMarkdown } from './clipboardMarkdown';

it.each([
  ['<p><strong>Two nurses</strong> and <em>one doctor</em></p>', '**Two nurses** and *one doctor*'],
  ['<b style="font-weight: normal"><span style="font-weight: 700">Bold</span> <span style="font-style: italic">italic</span></b>', '**Bold** *italic*'],
  ['<b> bold <strong>nested</strong> </b>', '**bold nested**'],
  ['<p><b>First</b><br>line</p><p>Second</p>', '**First**\nline\n\nSecond'],
  ['<a href="https://example.com/a(b)?q=x&amp;y=z">A [link]</a>', '[A \\[link\\]](https://example.com/a%28b%29?q=x&y=z)'],
  ['<b>Use *literally*</b><script>alert(1)</script>', '**Use \\*literally\\***'],
  ['<ul><li><b>A</b></li><li>B</li></ul>', '- **A**\n\n- B'],
  ['<b>中文</b> <a href="mailto:ward@example.com">Email</a>', '**中文** [Email](mailto:ward@example.com)'],
])('converts basic formatting: %s', (html, expected) => {
  expect(clipboardHtmlToMarkdown(html)).toBe(expected);
});

it.each(['', '<div>Plain **Markdown**</div>', '<a href="javascript:alert(1)">label</a>', '<a href="/relative">label</a>', '<b> </b>'])('leaves ordinary paste to the browser: %s', html => {
  expect(clipboardHtmlToMarkdown(html)).toBeNull();
});

it.each([
  '<table><tr><td><b>Person</b></td><td>Day</td></tr><tr><td>P1</td><td>2</td></tr></table>',
  '<b>Keep this YAML:</b><pre>people:\n  - id: P1\n</pre>',
])('uses plain text for clipboard structures that basic Markdown conversion cannot preserve: %s', html => {
  expect(clipboardHtmlToMarkdown(html)).toBeNull();
});
