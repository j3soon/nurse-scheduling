"""Render assistant Markdown text for user-visible AI assertions."""

# This file is part of Nurse Scheduling Project.
# SPDX-License-Identifier: AGPL-3.0-or-later
# This file is mostly AI generated.

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
    for token in tokens:
        if token.type in {"link_open"}:
            protected = True
        elif token.type in {"link_close"}:
            protected = False
        elif token.type in {"text", "image"}:
            chunks.append((token.content, not protected))
        elif token.type in {"code_inline", "html_inline"}:
            chunks.append((token.content, False))
        elif token.type in {"softbreak", "hardbreak"}:
            chunks.append(("\n", False))
    return chunks


def displayed_text(markdown: str) -> str:
    """Apply the frontend's OpenCC dictionary only to rendered prose nodes."""
    chunks: list[tuple[str, bool]] = []
    in_blockquote = False
    for token in MARKDOWN.parse(markdown):
        if token.type == "blockquote_open":
            in_blockquote = True
        elif token.type == "blockquote_close":
            in_blockquote = False
        elif token.type == "inline":
            chunks.extend(_inline_chunks(token.children or [], protected=in_blockquote))
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
