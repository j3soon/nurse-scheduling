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


def inspect_pdf(
    path: Path,
    *,
    page_number: int | None = None,
    max_pages: int = 10,
    max_chars_per_page: int = 3_000,
    render: bool = False,
    output_directory: Path = Path("/workspace/rendered-pages"),
    max_render_pixels: int = 4_000_000,
) -> dict[str, Any]:
    """Return text by page and optionally a visual rendering of one page."""
    if not 1 <= max_pages <= 100 or not 1 <= max_chars_per_page <= 10_000 or max_render_pixels <= 0:
        raise ValueError("Select 1-100 pages and 1-10,000 characters per page")
    if render and page_number is None:
        raise ValueError("Select one page with --page before rendering")
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
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
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-chars-per-page", type=int, default=3_000)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("/workspace/rendered-pages"))
    args = parser.parse_args()
    result = inspect_pdf(
        args.path,
        page_number=args.page,
        max_pages=args.max_pages,
        max_chars_per_page=args.max_chars_per_page,
        render=args.render,
        output_directory=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
