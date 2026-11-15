/* SPDX-License-Identifier: AGPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 Johnson Sun
 */
// This code is mostly AI generated.

// The offline export keeps original text nodes and only changes their display.
(() => {
  const toggle = document.getElementById('convert-chinese');
  const convert = OpenCC.Converter({ from: 'cn', to: 'twp' });
  const originals = new Map();
  document.querySelectorAll('.message.assistant .content').forEach(content => {
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!node.parentElement.closest('pre, code, blockquote, a')) originals.set(node, node.nodeValue);
    }
  });
  const update = () => {
    for (const [node, original] of originals) node.nodeValue = toggle.checked ? convert(original) : original;
  };
  toggle.disabled = false;
  toggle.addEventListener('change', update);
  update();
})();
