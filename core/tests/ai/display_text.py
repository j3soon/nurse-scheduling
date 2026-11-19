"""Render assistant Markdown text for user-visible AI assertions."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This test is mostly AI generated.

import json
import subprocess
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

OPENCC_BUNDLE = Path(__file__).resolve().parents[3] / "thirdparty/opencc/cn2t.js"
OPENCC_SCRIPT = """
const { Converter } = require(process.argv[1]);
const convert = Converter({ from: 'cn', to: 'twp' });
const chunks = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(chunks.map(convert)));
"""
MARKDOWN = MarkdownIt("gfm-like2", {"html": False, "alerts": False})


def _inline_chunks(tokens: list[Token], *, protected: bool = False) -> list[tuple[str, bool]]:
    chunks = []
    in_link = False
    for token in tokens:
        if token.type == "link_open":
            in_link = True
        elif token.type == "link_close":
            in_link = False
        elif token.type in {"text", "image"}:
            chunks.append((token.content, not (protected or in_link)))
        elif token.type in {"code_inline", "html_inline"}:
            chunks.append((token.content, False))
        elif token.type in {"softbreak", "hardbreak"}:
            chunks.append(("\n", False))
    return chunks


def displayed_text(markdown: str) -> str:
    """Apply the frontend's OpenCC dictionary only to rendered prose nodes."""
    chunks: list[tuple[str, bool]] = []
    blockquote_depth = 0
    for token in MARKDOWN.parse(markdown):
        if token.type in {"blockquote_open", "blockquote_close"}:
            blockquote_depth += token.nesting
        elif token.type == "inline":
            chunks.extend(_inline_chunks(token.children or [], protected=blockquote_depth > 0))
        elif token.type in {"fence", "code_block"}:
            chunks.append((token.content, False))
        elif token.type in {"td_close", "th_close"}:
            chunks.append((" ", False))
        elif token.type in {"paragraph_close", "heading_close", "list_item_close", "tr_close"}:
            chunks.append(("\n", False))
    prose = [value for value, convert in chunks if convert]
    if not prose:
        return "".join(value for value, _ in chunks)
    result = subprocess.run(
        ["node", "-e", OPENCC_SCRIPT, str(OPENCC_BUNDLE)],
        input=json.dumps(prose, ensure_ascii=False),
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=10,
    )
    converted = iter(json.loads(result.stdout))
    return "".join(next(converted) if convert else value for value, convert in chunks)
