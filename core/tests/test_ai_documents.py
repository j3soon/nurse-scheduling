"""Tests for bounded AI document extraction."""

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

from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter

from nurse_scheduling.ai.app import create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.documents import (
    DocumentExtractionLimits,
    DocumentLimitError,
    InvalidDocumentError,
    extract_document_text,
)
from nurse_scheduling.ai.provider import ChatMessage


class FakeProvider:
    """Record the extracted provider prompt."""

    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    async def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        yield "Document answer"


def _limits(**overrides: int) -> DocumentExtractionLimits:
    limits = DocumentExtractionLimits(
        max_text_chars=50_000,
        max_pdf_pages=100,
        max_xlsx_sheets=20,
        max_xlsx_cells=100_000,
        max_xlsx_uncompressed_bytes=50_000_000,
    )
    return replace(limits, **overrides)


def _pdf_with_text(text: str) -> bytes:
    """Build a small dependency-free PDF fixture containing one text object."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode())
        result.extend(value)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(result)


def _xlsx_with_formula() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Coverage"
    worksheet["A1"] = "Day"
    worksheet["A2"] = 1
    worksheet["B2"] = 2
    worksheet["C2"] = "=SUM(A2:B2)"
    worksheet["C3"] = "=A2"
    initial = BytesIO()
    workbook.save(initial)

    output = BytesIO()
    with ZipFile(BytesIO(initial.getvalue())) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                original = b'<c r="C2"><f>SUM(A2:B2)</f><v /></c>'
                assert original in content
                content = content.replace(original, b'<c r="C2"><f>SUM(A2:B2)</f><v>3</v></c>')
            target.writestr(entry, content)
    return output.getvalue()


def _pdf_from_writer(*, pages: int = 1, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_and_xlsx_are_extracted_for_one_provider_request() -> None:
    provider = FakeProvider()
    settings = AiSettings(
        provider_base_url="https://provider.example/v1",
        provider_api_key="test-token",
        provider_model="test-model",
        cookie_secure=False,
    )
    client = TestClient(create_app(settings=settings, provider=provider))
    session = client.post("/sessions", json={"schedule_yaml": "description: test"})

    response = client.post(
        f"/sessions/{session.json()['id']}/messages",
        data={"message": "Read both documents."},
        files=[
            ("documents", ("notes.pdf", _pdf_with_text("Alice works Monday"), "application/pdf")),
            (
                "documents",
                (
                    "coverage.xlsx",
                    _xlsx_with_formula(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
    )

    assert response.status_code == 200
    prompt = provider.calls[0][-1]["content"]
    assert isinstance(prompt, str)
    assert "Alice works Monday" in prompt
    assert 'C2: formula \\"=SUM(A2:B2)\\", cached value 3' in prompt
    assert 'C3: formula \\"=A2\\", cached value unavailable' in prompt


def test_pdf_extraction_marks_pages_without_embedded_text() -> None:
    text = extract_document_text("scan.pdf", _pdf_from_writer(), _limits())

    assert text == "--- PDF page 1 ---\n[No extractable text. OCR was not performed.]"


@pytest.mark.parametrize(
    ("data", "limits", "expected_error"),
    [
        (_pdf_from_writer(pages=2), _limits(max_pdf_pages=1), "PDF attachment has too many pages."),
        (_pdf_from_writer(password="secret"), _limits(), "Encrypted PDF attachments are not supported."),
        (b"not pdf", _limits(), "PDF content does not match its filename."),
    ],
)
def test_pdf_rejects_unsupported_or_bounded_content(
    data: bytes,
    limits: DocumentExtractionLimits,
    expected_error: str,
) -> None:
    error_type = DocumentLimitError if "too many" in expected_error else InvalidDocumentError
    with pytest.raises(error_type, match=expected_error):
        extract_document_text("notes.pdf", data, limits)


def test_xlsx_extraction_preserves_formulas_and_cached_values() -> None:
    text = extract_document_text("coverage.xlsx", _xlsx_with_formula(), _limits())

    assert '--- XLSX sheet "Coverage" ---' in text
    assert 'A1: "Day"' in text
    assert 'C2: formula "=SUM(A2:B2)", cached value 3' in text
    assert 'C3: formula "=A2", cached value unavailable' in text


@pytest.mark.parametrize(
    ("limits", "expected_error"),
    [
        (_limits(max_xlsx_sheets=0), "XLSX attachment has too many sheets."),
        (_limits(max_xlsx_cells=2), "XLSX attachment contains too many cells."),
        (_limits(max_xlsx_uncompressed_bytes=1), "XLSX attachment expands beyond the allowed size."),
    ],
)
def test_xlsx_enforces_structural_limits(limits: DocumentExtractionLimits, expected_error: str) -> None:
    with pytest.raises(DocumentLimitError, match=expected_error):
        extract_document_text("coverage.xlsx", _xlsx_with_formula(), limits)


def test_xlsx_rejects_content_that_is_not_an_ooxml_workbook() -> None:
    with pytest.raises(InvalidDocumentError, match="XLSX content does not match its filename"):
        extract_document_text("coverage.xlsx", b"not xlsx", _limits())


def test_text_extraction_has_a_separate_prompt_size_limit() -> None:
    with pytest.raises(DocumentLimitError, match="Document extracted text is too large"):
        extract_document_text("notes.txt", b"12345", _limits(max_text_chars=4))
