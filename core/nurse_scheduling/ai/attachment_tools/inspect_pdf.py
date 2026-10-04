"""Inspect bounded PDF text and optionally render a selected page to PNG."""

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

# This code is mostly AI generated.

import argparse
import json
import math
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def _render_page(path: Path, page_number: int, output_directory: Path, max_pixels: int) -> dict[str, Any]:
    """Render an entire page, including vector content, within a pixel budget."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(path)
    try:
        page = document[page_number - 1]
        try:
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                raise ValueError("PDF page has invalid dimensions")
            scale = min(2.0, math.sqrt(max_pixels / (width * height)))
            bitmap = page.render(scale=scale)
            try:
                output_directory.mkdir(parents=True, exist_ok=True)
                destination = output_directory / f"page-{page_number:03d}.png"
                image = bitmap.to_pil()
                try:
                    image.save(destination, "PNG")
                    return {"path": str(destination), "width": image.width, "height": image.height}
                finally:
                    image.close()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def _search_text(reader: PdfReader, path: Path, needle: str, max_pages: int, max_matches: int) -> dict[str, Any]:
    """Return bounded literal matches from already loaded PDF pages."""
    scanned = min(len(reader.pages), max_pages)
    matches, no_text = [], []
    for number in range(scanned):
        text = (reader.pages[number].extract_text() or "").strip()
        if not text:
            no_text.append(number + 1)
        index = text.lower().find(needle.lower())
        if index >= 0:
            start = max(0, index - 80)
            matches.append({"page": number + 1, "excerpt": text[start : start + 400]})
    return {
        "path": str(path),
        "page_count": len(reader.pages),
        "pages_scanned": scanned,
        "pages_truncated": scanned < len(reader.pages),
        "matched_pages": len(matches),
        "matches": matches[:max_matches],
        "matches_truncated": len(matches) > max_matches,
        "pages_without_extractable_text": no_text,
        "ocr_performed": False,
    }


def inspect_pdf(
    path: Path,
    *,
    page_number: int | None = None,
    max_pages: int | None = None,
    find: str | None = None,
    max_matches: int = 20,
    max_chars_per_page: int = 3_000,
    render: bool = False,
    output_directory: Path = Path("/workspace/rendered-pages"),
    max_render_pixels: int = 4_000_000,
) -> dict[str, Any]:
    """Return text by page and optionally a visual rendering of one page."""
    if find is not None:
        if not find.strip() or (max_pages is not None and max_pages <= 0) or max_matches <= 0:
            raise ValueError("Provide nonempty text and positive limits")
        if page_number is not None or render:
            raise ValueError("Use --find separately from --page and --render")
        max_pages = min(100 if max_pages is None else max_pages, 100)
        max_matches = min(max_matches, 100)
    elif max_pages is None:
        max_pages = 10
    if not 1 <= max_pages <= 100 or not 1 <= max_chars_per_page <= 10_000 or max_render_pixels <= 0:
        raise ValueError("Select 1-100 pages and 1-10,000 characters per page")
    if render and page_number is None:
        raise ValueError("Select one page with --page before rendering")
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    if find is not None:
        return _search_text(reader, path, find, max_pages, max_matches)
    page_count = len(reader.pages)
    if page_number is not None:
        if not 1 <= page_number <= page_count:
            raise ValueError(f"Page must be between 1 and {page_count}")
        numbers = [page_number]
    else:
        numbers = list(range(1, min(page_count, max_pages) + 1))

    pages = []
    for number in numbers:
        text = (reader.pages[number - 1].extract_text() or "").strip()
        entry: dict[str, Any] = {
            "page": number,
            "text": text[:max_chars_per_page],
            "text_truncated": len(text) > max_chars_per_page,
            "has_extractable_text": bool(text),
        }
        if render:
            entry["rendered_image"] = _render_page(path, number, output_directory, max_render_pixels)
        pages.append(entry)
    return {
        "path": str(path),
        "page_count": page_count,
        "pages": pages,
        "pages_truncated": page_number is None and page_count > max_pages,
        "ocr_performed": False,
    }


def main() -> None:
    """Inspect a PDF from the sandbox shell."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--page", type=int)
    parser.add_argument("--find", help="Literal text to find across pages, case insensitive.")
    parser.add_argument("--max-pages", type=int, help="Maximum pages, default 10 for inspection or 100 for search.")
    parser.add_argument("--max-matches", type=int, default=20)
    parser.add_argument("--max-chars-per-page", type=int, default=3_000)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("/workspace/rendered-pages"))
    args = parser.parse_args()
    result = inspect_pdf(
        args.path,
        page_number=args.page,
        max_pages=args.max_pages,
        find=args.find,
        max_matches=args.max_matches,
        max_chars_per_page=args.max_chars_per_page,
        render=args.render,
        output_directory=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=None if args.find is not None else 2))


if __name__ == "__main__":
    main()
