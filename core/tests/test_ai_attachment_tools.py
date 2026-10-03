"""Tests for trusted sandbox attachment helper scripts."""

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

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from nurse_scheduling.ai.attachment_tools.inspect_pdf import inspect_pdf
from nurse_scheduling.ai.attachment_tools.inspect_xlsx import inspect_workbook

from .ai_eval.attachment_fixtures import load_attachment_fixtures


def test_evaluation_workbooks_preserve_stale_caches_colors_and_reproducible_bytes(tmp_path: Path):
    names = ("formula-xlsx", "colored-xlsx")
    attachments = load_attachment_fixtures(names)
    assert [attachment.data for attachment in attachments] == [
        attachment.data for attachment in load_attachment_fixtures(names)
    ]
    for attachment in attachments:
        with ZipFile(BytesIO(attachment.data)) as archive:
            assert all(entry.date_time == (2020, 1, 1, 0, 0, 0) for entry in archive.infolist())
    path = tmp_path / "formulas.xlsx"
    path.write_bytes(attachments[0].data)
    checks = inspect_workbook(path, sheet_name="Staffing checks")["sheets"][0]["rows"]
    assert checks[2]["values"][2] == {"cell": "C3", "formula": "=B3*2", "cached_value": 11}
    assert checks[3]["values"][2] == {"cell": "C4", "formula": "=SUM(B3:B4)", "cached_value": 10}
    assert checks[4]["values"][2] == {"cell": "C5", "formula": "=B5+1", "cached_value": None}
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(attachments[1].data))
    assert workbook.active["A2"].fill.fgColor.rgb == "00FFF2CC"
    assert workbook.active["A3"].fill.patternType is None
    assert workbook.active["A4"].fill.fgColor.rgb == "00FFF2CC"
    workbook.close()


def test_inspection_pdf_fixtures_are_stable_and_visual_page_requires_layout(tmp_path: Path):
    for name in ("text-inspection-pdf", "visual-inspection-pdf"):
        attachment = load_attachment_fixtures((name,))[0]
        assert attachment.data == load_attachment_fixtures((name,))[0].data
        path = tmp_path / attachment.filename
        path.write_bytes(attachment.data)
        result = inspect_pdf(path, page_number=3, render=True, output_directory=tmp_path / name)
        assert result["page_count"] == 4
        page = result["pages"][0]
        if name == "text-inspection-pdf":
            assert "TEXT CHECK 5703" in page["text"]
        else:
            assert "BETA CHECK 6428" in page["text"]
            assert "ALPHA CHECK 9137" in page["text"]
            with Image.open(page["rendered_image"]["path"]) as image:
                rgb = image.convert("RGB")
                assert rgb.getpixel((100, 150)) == (51, 128, 255)
                assert rgb.getpixel((100, 450)) == (255, 217, 26)


def test_workbook_inspector_reads_every_sheet_including_hidden_sheets(tmp_path: Path):
    path = tmp_path / "multi-sheet.xlsx"
    workbook = Workbook()
    first = workbook.active
    first.title = "First"
    first.append(["person", "shift"])
    first.append(["Alice", "Day"])
    second = workbook.create_sheet("Second")
    second.append(["Bob", "Night"])
    hidden = workbook.create_sheet("Hidden")
    hidden.sheet_state = "hidden"
    hidden.append(["Private", "Value"])
    workbook.save(path)

    result = inspect_workbook(path)

    assert result["sheet_names"] == ["First", "Second", "Hidden"]
    assert [sheet["name"] for sheet in result["sheets"]] == ["First", "Second", "Hidden"]
    assert result["sheets"][1]["rows"] == [{"row": 1, "values": ["Bob", "Night"]}]
    assert result["sheets"][2]["state"] == "hidden"


def test_workbook_inspector_shows_formulas_and_last_saved_values(tmp_path: Path):
    path = tmp_path / "formula.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = 2
    worksheet["A2"] = 3
    worksheet["A3"] = "=SUM(A1:A2)"
    source = BytesIO()
    workbook.save(source)
    workbook.close()
    source.seek(0)
    with ZipFile(source) as archive, ZipFile(path, "w", ZIP_DEFLATED) as updated:
        for entry in archive.infolist():
            content = archive.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b"<f>SUM(A1:A2)</f><v />", b"<f>SUM(A1:A2)</f><v>5</v>")
            updated.writestr(entry, content)

    result = inspect_workbook(path)

    assert result["cached_values_are_last_saved_not_recalculated"]
    assert result["sheets"][0]["rows"][2] == {
        "row": 3,
        "values": [{"cell": "A3", "formula": "=SUM(A1:A2)", "cached_value": 5}],
    }


def test_workbook_inspector_selects_later_rows_and_sheets(tmp_path: Path):
    path = tmp_path / "large.xlsx"
    workbook = Workbook()
    workbook.active["A201"] = "Later row"
    for index in range(21):
        workbook.create_sheet(f"Sheet {index}")
    workbook["Sheet 20"]["C4"] = "Later sheet"
    workbook.save(path)

    overview = inspect_workbook(path)
    later_row = inspect_workbook(path, start_row=201, max_rows=1, max_columns=1)
    later_sheet = inspect_workbook(path, sheet_name="Sheet 20", start_row=4, start_column=3, max_rows=1, max_columns=1)

    assert overview["sheets_truncated"]
    assert overview["sheets"][0]["truncated"]
    assert later_row["sheets"][0]["rows"] == [{"row": 201, "values": ["Later row"]}]
    assert later_sheet["sheets"][0]["rows"] == [{"row": 4, "values": ["Later sheet"]}]
    assert later_sheet["sheets"][0]["first_column"] == 3


def _text_pdf(path: Path) -> None:
    writer = PdfWriter()
    for label in ("First page", "Second page"):
        page = writer.add_blank_page(width=300, height=200)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 18 Tf 40 100 Td ({label}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def test_pdf_inspector_extracts_text_by_page_and_reports_truncation(tmp_path: Path):
    path = tmp_path / "text.pdf"
    _text_pdf(path)

    first = inspect_pdf(path, max_pages=1)
    second = inspect_pdf(path, page_number=2, render=True, output_directory=tmp_path / "rendered")

    assert first["page_count"] == 2
    assert first["pages_truncated"]
    assert "First page" in first["pages"][0]["text"]
    assert second["pages"][0]["page"] == 2
    assert "Second page" in second["pages"][0]["text"]
    assert not second["ocr_performed"]
    with Image.open(second["pages"][0]["rendered_image"]["path"]) as image:
        assert image.convert("L").getextrema()[0] < 255

    shortened = inspect_pdf(path, page_number=2, max_chars_per_page=6)
    assert shortened["pages"][0]["text"] == "Second"
    assert shortened["pages"][0]["text_truncated"]


def test_pdf_inspector_renders_an_image_only_page(tmp_path: Path):
    path = tmp_path / "image.pdf"
    Image.new("RGB", (100, 80), "blue").save(path, "PDF")

    result = inspect_pdf(path, page_number=1, render=True, output_directory=tmp_path / "rendered")

    page = result["pages"][0]
    assert not page["has_extractable_text"]
    image_path = Path(page["rendered_image"]["path"])
    with Image.open(image_path) as image:
        assert image.format == "PNG"
        assert image.width > 0 and image.height > 0


def test_pdf_inspector_requires_a_selected_page_for_rendering(tmp_path: Path):
    path = tmp_path / "image.pdf"
    Image.new("RGB", (10, 10), "red").save(path, "PDF")

    with pytest.raises(ValueError, match="Select one page"):
        inspect_pdf(path, render=True)


def test_xlsx_styles_preserve_blank_cells_and_distinguish_stored_color_sources(tmp_path):
    from openpyxl.styles import Alignment, Border, Color, Font, GradientFill, PatternFill, Side

    path = tmp_path / "styles.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["B4"] = 1
    sheet["B4"].font = Font(color="FFFF0000", bold=True)
    sheet["B4"].fill = PatternFill("solid", fgColor="FFFFF2CC")
    sheet["C4"] = 1
    sheet["C4"].font = Font(color="FF000000")
    sheet["D4"].fill = PatternFill("solid", fgColor=Color(theme=4, tint=0.4))
    sheet["E4"] = 3.25
    sheet["E4"].font = Font(color=Color(indexed=10))
    sheet["E4"].alignment = Alignment(horizontal="center", wrap_text=True)
    sheet["E4"].border = Border(bottom=Side(style="thin", color="FF112233"))
    sheet["E4"].number_format = "0.00"
    sheet["F4"].fill = GradientFill(stop=("FF112233", "FF445566"))
    from copy import copy

    sheet["G4"].fill = copy(sheet["D4"].fill)
    sheet["H4"] = "=E4*2"
    sheet["H4"].font = Font(color=Color(theme=0))
    workbook.save(path)
    plain = inspect_workbook(path, start_row=4, start_column=2, max_rows=1, max_columns=7)
    assert "styles" not in plain
    assert plain["sheets"][0]["rows"][0]["values"][2] is None
    result = inspect_workbook(path, start_row=4, start_column=2, max_rows=1, max_columns=7, styles=True)
    cells = {cell["cell"]: cell for cell in result["sheets"][0]["rows"][0]["values"]}
    style = lambda coordinate: result["styles"][cells[coordinate]["style"]]
    assert style("B4")["font"]["color"] == {"type": "rgb", "value": "FFFF0000"}
    assert style("C4")["font"]["color"] == {"type": "rgb", "value": "FF000000"}
    assert style("B4")["font"]["bold"]
    assert style("B4")["fill"]["foreground"]["value"] == "FFFFF2CC"
    assert cells["D4"]["value"] is None
    assert cells["D4"]["style"] == cells["G4"]["style"]
    assert style("D4")["fill"]["foreground"] == {"type": "theme", "value": 4, "tint": 0.4, "base_rgb": "4F81BD"}
    assert style("E4")["font"]["color"] == {"type": "indexed", "value": 10, "base_rgb": "00FF0000"}
    assert style("E4")["number_format"] == "0.00"
    assert style("E4")["alignment"] == {"horizontal": "center", "wrapText": True}
    assert style("E4")["borders"]["bottom"]["style"] == "thin"
    assert style("F4")["fill"]["stops"][1]["color"]["value"] == "FF445566"
    assert cells["H4"]["formula"] == "=E4*2"
    assert cells["H4"]["cached_value"] is None
    assert style("H4")["font"]["color"]["base_rgb"] == "FFFFFF"
    assert result["styles_are_stored_not_rendered"]
    assert result["cells_without_style_use"] == "0"
    assert result["styles"]["0"]["font"]["color"]["base_rgb"] == "000000"


def test_styled_request_case_oracle_matches_source_cells_and_saved_caches():
    import json

    from openpyxl import load_workbook

    attachment = load_attachment_fixtures(("styled-requests-xlsx",))[0]
    assert attachment.data == load_attachment_fixtures(("styled-requests-xlsx",))[0].data
    case = json.loads(
        (
            Path(__file__).parent / "ai_eval/cases/basics/14-attachment-inspection/xlsx-styled-requests-and-caches.json"
        ).read_text()
    )
    book = load_workbook(BytesIO(attachment.data), data_only=False)
    cached = load_workbook(BytesIO(attachment.data), data_only=True)
    seniors = []
    off_days = {}
    for row in book["Requests"].iter_rows(min_row=2):
        name = row[0].value
        if row[0].fill.fgColor.rgb == "FFFFF2CC":
            seniors.append(name)
        off_days[name] = [cell.column - 1 for cell in row[1:] if cell.font.color.rgb == "FFFF0000"]
        assert all(cell.value == 1 for cell in row[1:])
    capacity = {
        row[0].value: cached["Capacity audit"][row[2].coordinate].value
        for row in book["Capacity audit"].iter_rows(min_row=2)
    }
    assert case["answer_json"] == {
        "seniorNames": sorted(seniors),
        "offDays": off_days,
        "savedCapacity": capacity,
        "formulaCount": 3,
    }
    assert book["Capacity audit"].sheet_state == "hidden"
    assert all(book["Capacity audit"].cell(row, 3).data_type == "f" for row in range(2, 5))
    assert capacity["Day"] != book["Capacity audit"]["B2"].value * 2
    book.close()
    cached.close()


def test_overview_preserves_all_sheet_headers_without_opening_cells(tmp_path, monkeypatch):
    attachment = load_attachment_fixtures(["inventory-xlsx"])[0]
    path = tmp_path / "tabs.xlsx"
    path.write_bytes(attachment.data)
    from openpyxl.worksheet._read_only import ReadOnlyWorksheet

    from nurse_scheduling.ai.attachment_tools import inspect_xlsx

    loads = []
    original_load = inspect_xlsx.load_workbook

    def observed_load(*args, **kwargs):
        loads.append(kwargs)
        return original_load(*args, **kwargs)

    def unexpected_cell_read(*args, **kwargs):
        raise AssertionError("An overview must not read cell values")

    monkeypatch.setattr(ReadOnlyWorksheet, "iter_rows", unexpected_cell_read)
    monkeypatch.setattr(inspect_xlsx, "load_workbook", observed_load)
    result = inspect_workbook(path, overview=True)
    assert len(loads) == 1
    assert loads[0]["data_only"] is False
    assert result["sheet_count"] == 24
    assert sum(s["state"] != "visible" for s in result["sheets"]) == 3
    assert sum(s["reported_rows"] >= 80 and s["reported_columns"] >= 30 for s in result["sheets"]) == 12
    assert not result["sheets_truncated"]
    assert all("rows" not in s for s in result["sheets"])
    assert inspect_workbook(path, sheet_name="Tab 24", overview=True)["sheets"][0]["state"] == "veryHidden"
    with pytest.raises(ValueError, match="Unknown sheet"):
        inspect_workbook(path, sheet_name="missing", overview=True)


def test_overview_bounds_metadata_and_reports_truncation(tmp_path):
    book = Workbook()
    for i in range(104):
        book.create_sheet(f"Sheet {i}")
    path = tmp_path / "many.xlsx"
    book.save(path)
    book.close()
    result = inspect_workbook(path, overview=True)
    assert result["sheet_count"] == 105
    assert len(result["sheets"]) == 100
    assert result["sheets_truncated"]


def test_pdf_search_finds_later_text_with_bounded_excerpt(tmp_path, monkeypatch):
    attachment = load_attachment_fixtures(["search-pdf"])[0]
    path = tmp_path / "manual.pdf"
    path.write_bytes(attachment.data)
    from nurse_scheduling.ai.attachment_tools import inspect_pdf as pdf_tools

    calls = []
    original_reader = pdf_tools.PdfReader

    def observed_reader(*args, **kwargs):
        calls.append(args)
        return original_reader(*args, **kwargs)

    def unexpected_render(*args, **kwargs):
        raise AssertionError("Text search must not render pages")

    monkeypatch.setattr(pdf_tools, "PdfReader", observed_reader)
    monkeypatch.setattr(pdf_tools, "_render_page", unexpected_render)
    result = inspect_pdf(path, find="continuity plan")
    assert len(calls) == 1
    assert result["page_count"] == result["pages_scanned"] == 28
    assert result["matched_pages"] == 1
    assert result["matches"][0]["page"] == 26
    assert "BRIDGE 6842" in result["matches"][0]["excerpt"]
    assert len(result["matches"][0]["excerpt"]) <= 400
    assert not result["pages_truncated"]
    assert not result["ocr_performed"]
    limited = inspect_pdf(path, find="continuity plan", max_pages=10)
    assert limited["matched_pages"] == 0
    assert limited["pages_truncated"]
    many = inspect_pdf(path, find="Routine", max_matches=2)
    assert many["matched_pages"] == 28
    assert len(many["matches"]) == 2 and many["matches_truncated"]


def test_pdf_search_reports_scanned_pages_and_rejects_empty_terms(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(load_attachment_fixtures(["image-pdf"])[0].data)
    result = inspect_pdf(path, find="not present")
    assert result["pages_without_extractable_text"] == [1]
    assert result["matched_pages"] == 0 and not result["ocr_performed"]
    with pytest.raises(ValueError, match="nonempty"):
        inspect_pdf(path, find=" ")


@pytest.mark.parametrize("options", [{"page_number": 1}, {"render": True}])
def test_pdf_search_rejects_conflicting_page_modes(tmp_path, options):
    with pytest.raises(ValueError, match="separately"):
        inspect_pdf(tmp_path / "missing.pdf", find="text", **options)
