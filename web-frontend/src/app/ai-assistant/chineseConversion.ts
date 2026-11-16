/* SPDX-License-Identifier: AGPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 Johnson Sun
 */
// This code is mostly AI generated.

import { Converter } from '../../../../thirdparty/opencc/cn2t';

type ProseNode = { type: string; tagName?: string; value?: string; properties?: { alt?: string }; children?: ProseNode[] };

let converter: ((text: string) => string) | undefined;

// Convert parsed prose, so Markdown syntax and literal source text stay exact.
export function traditionalChinese() {
  return (tree: ProseNode) => {
    const convert = converter ??= Converter({ from: 'cn', to: 'twp' });
    const visit = (node: ProseNode) => {
      if (node.type === 'element' && ['pre', 'code', 'blockquote', 'a'].includes(node.tagName ?? '')) return;
      if (node.type === 'text' && node.value !== undefined) node.value = convert(node.value);
      if (node.type === 'element' && node.tagName === 'img' && typeof node.properties?.alt === 'string') {
        node.properties.alt = convert(node.properties.alt);
      }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
}
