"""Regression checks for attachment evaluation fixtures and inspection paths."""

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

from pathlib import Path
from zipfile import ZipFile

import pytest

from nurse_scheduling.ai.attachment_tools.inspect_pdf import inspect_pdf
from nurse_scheduling.ai.attachment_tools.inspect_xlsx import inspect_workbook
from nurse_scheduling.ai.pi.read import ReadInput, render_read_result

from .ai_eval.attachment_fixtures import load_attachment_fixtures


def _fixture(name: str, tmp_path: Path) -> Path:
    attachment = load_attachment_fixtures([name])[0]
    path = tmp_path / attachment.filename
    path.write_bytes(attachment.data)
    return path


def test_xlsx_fixture_requires_reading_the_non_first_sheet(tmp_path: Path):
    workbook = inspect_workbook(_fixture("multi-sheet-xlsx", tmp_path))

    assert workbook["sheet_names"] == ["Overview", "Night assignment"]
    assert all("NIGHT OWL 7429" not in str(row) for row in workbook["sheets"][0]["rows"])
    assert "NIGHT OWL 7429" in str(workbook["sheets"][1]["rows"])


def test_pdf_fixture_renders_a_page_read_can_return_to_the_model(tmp_path: Path):
    manifest = inspect_pdf(
        _fixture("image-pdf", tmp_path),
        page_number=1,
        render=True,
        output_directory=tmp_path / "rendered-pages",
    )

    assert manifest["pages"][0]["has_extractable_text"] is False
    image_path = Path(manifest["pages"][0]["rendered_image"]["path"])
    result = render_read_result(image_path.read_bytes(), ReadInput(str(image_path)))
    assert result.image is not None


@pytest.mark.parametrize(
    ("fixture_name", "media_path"),
    [
        ("image-docx", "word/media/image1.png"),
        ("image-pptx", "ppt/media/image1.png"),
    ],
)
def test_ooxml_fixture_contains_an_image_read_can_return_to_the_model(
    fixture_name: str,
    media_path: str,
    tmp_path: Path,
):
    with ZipFile(_fixture(fixture_name, tmp_path)) as archive:
        image = archive.read(media_path)

    result = render_read_result(image, ReadInput(media_path))
    assert result.image is not None
