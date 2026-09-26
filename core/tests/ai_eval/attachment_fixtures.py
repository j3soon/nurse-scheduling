"""Deterministic binary attachments for real-provider AI evaluations."""

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

# This test fixture generator is mostly AI generated.

from collections.abc import Callable, Sequence
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont

from nurse_scheduling.ai.workspace import SandboxAttachment


def _label_image(label: str) -> bytes:
    image = Image.new("RGB", (1_200, 360), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
    except OSError:  # pragma: no cover - CI and the sandbox image include DejaVu
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), label, font=font)
    draw.text(
        ((image.width - (box[2] - box[0])) / 2, (image.height - (box[3] - box[1])) / 2),
        label,
        fill="black",
        font=font,
    )
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _xlsx() -> bytes:
    workbook = Workbook()
    workbook.active.title = "Overview"
    workbook.active.append(["Department", "Status"])
    workbook.active.append(["Ward A", "Ready"])
    hidden = workbook.create_sheet("Night assignment")
    hidden.append(["Field", "Value"])
    hidden.append(["handover code", "NIGHT OWL 7429"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _pdf() -> bytes:
    image = Image.open(BytesIO(_label_image("PDF VISION 3816"))).convert("RGB")
    output = BytesIO()
    image.save(output, "PDF", resolution=150)
    return output.getvalue()


def _zip_package(files: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def _docx() -> bytes:
    image = _label_image("DOCX VISION 6248")
    return _zip_package(
        {
            "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
            "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
            "word/document.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><w:body><w:p><w:r><w:drawing><wp:inline><a:graphic><a:graphicData><pic:pic><pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p></w:body></w:document>""",
            "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>""",
            "word/media/image1.png": image,
        }
    )


def _pptx() -> bytes:
    image = _label_image("SLIDE VISION 9531")
    return _zip_package(
        {
            "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>""",
            "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>""",
            "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>""",
            "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>""",
            "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:cSld><p:spTree><p:pic><p:blipFill><a:blip r:embed="rId1"/></p:blipFill></p:pic></p:spTree></p:cSld></p:sld>""",
            "ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/></Relationships>""",
            "ppt/media/image1.png": image,
        }
    )


_FIXTURES: dict[str, tuple[str, str, Callable[[], bytes]]] = {
    "multi-sheet-xlsx": (
        "ward-notes.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _xlsx,
    ),
    "image-pdf": ("scanned-note.pdf", "application/pdf", _pdf),
    "image-docx": (
        "illustrated-note.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        _docx,
    ),
    "image-pptx": (
        "briefing-slide.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        _pptx,
    ),
}


def attachment_fixture_names() -> frozenset[str]:
    """Return every attachment fixture accepted by the evaluation runner."""
    return frozenset(_FIXTURES)


def load_attachment_fixtures(names: Sequence[str]) -> tuple[SandboxAttachment, ...]:
    """Build named attachments without storing generated binaries in Git."""
    attachments = []
    for name in names:
        try:
            filename, media_type, build = _FIXTURES[name]
        except KeyError as exc:
            raise ValueError(f"Unknown attachment fixture: {name}") from exc
        attachments.append(SandboxAttachment(filename, media_type, build()))
    return tuple(attachments)
