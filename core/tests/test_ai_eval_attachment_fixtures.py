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

import csv
import hashlib
import json
import runpy
import sys
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook

from nurse_scheduling.ai.attachment_tools.inspect_pdf import inspect_pdf
from nurse_scheduling.ai.attachment_tools.inspect_xlsx import inspect_workbook
from nurse_scheduling.ai.pi.read import ReadInput, render_read_result
from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml

from .ai_eval.attachment_fixtures import load_attachment_fixtures
from .ai_eval.grading import RunOutcome, _check_yaml_generator, grade, load_cases
from .ai_eval.prompt_ladder import case_digest
from .ai_eval.runner import CASES, fixture_text


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


@pytest.mark.parametrize("order", ["forward", "reverse"])
def test_history_import_oracles_match_calendar_order_and_final_runs(order):
    attachment = load_attachment_fixtures([f"month-end-history-{order}-xlsx"])[0]
    assert attachment.data == load_attachment_fixtures([f"month-end-history-{order}-xlsx"])[0].data
    workbook = load_workbook(BytesIO(attachment.data), data_only=True)
    rows = list(workbook.active.values)
    histories = {}
    lines = []
    for person, *shifts in rows[1:]:
        history = [shift for _, shift in sorted(zip(rows[0][1:], shifts, strict=True))]
        histories[person] = history
        count = 0
        for shift in reversed(history):
            if shift != history[-1]:
                break
            count += 1
        lines.append(f"{person},{history[-1]},{count}")
    workbook.close()
    cases = {case.id: case for case in load_cases(CASES)}
    expected = "\n".join(sorted(lines)) + "\n"
    assert cases[f"month-end-history-{order}"].download_files == {"people-history.csv": expected}
    assert cases["month-end-full-history"].answer_json == {"histories": histories}
    parsed = list(csv.reader(StringIO(expected)))
    assert len({row[0] for row in parsed}) == len(histories)
    assert all(len(row) == 3 and row[2].isdigit() for row in parsed)


@pytest.mark.parametrize("order", ["forward", "reverse"])
def test_history_download_oracle_rejects_extra_runs_for_one_person(order):
    case = next(case for case in load_cases(CASES) if case.id == f"month-end-history-{order}")
    expected = case.download_files["people-history.csv"]
    activity = [{"kind": "tool", "name": "bash", "ok": True, "arguments": "{}", "result": "parsed"}]
    for data, accepted in [(expected, True), ("Ada,D,4\n" + expected, False)]:
        download = {"kind": "download", "files": {"people-history.csv": hashlib.sha256(data.encode()).hexdigest()}}
        assert grade(case, RunOutcome(activity=[*activity, download])).passed == accepted


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


@pytest.mark.parametrize("label", ["BETA CHECK 6428", "ALPHA CHECK 9137", "6428"])
def test_pdf_visual_oracle_accepts_equivalent_parsing_and_requires_the_complete_label(label: str):
    case = next(case for case in load_cases(CASES) if case.id == "pdf-visual-layout")
    outcome = RunOutcome(
        initial={},
        answer=json.dumps({"yellowCode": label}),
        activity=[{"kind": "tool", "name": "bash", "ok": True, "arguments": "{}", "result": "PDF parsed"}],
    )
    assert grade(case, outcome).passed == (label == "BETA CHECK 6428")


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


def test_yaml_generator_fixture_can_be_repaired_without_installation(tmp_path: Path, monkeypatch):
    from ruamel.yaml import YAML

    attachment = load_attachment_fixtures(["pyyaml-generator"])[0]
    output = tmp_path / "schedule.yaml"
    script = attachment.data.decode("utf-8").replace('"/workspace/schedule.yaml"', repr(str(output)))
    generator = tmp_path / "generate_schedule.py"
    generator.write_text(script)
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(ModuleNotFoundError):
        runpy.run_path(str(generator))
    repaired = script.replace("import yaml", "from ruamel.yaml import YAML").replace(
        "yaml.safe_dump(schedule, output, sort_keys=False)", "YAML().dump(schedule, output)"
    )
    generator.write_text(repaired)
    runpy.run_path(str(generator))
    case = next(case for case in load_cases(CASES) if case.id == "tool-yaml-generator-repair")
    activity = [
        {
            "kind": "tool",
            "name": "bash",
            "ok": True,
            "arguments": json.dumps({"command": f"python3 {generator}"}),
            "result": "Generated Minimal March schedule from attachment",
        }
    ]
    result = grade(
        case,
        RunOutcome(
            initial=YAML().load(fixture_text(case.fixture)),
            proposed=YAML().load(output.read_text()),
            activity=activity,
        ),
    )
    assert result.passed, result
    validation = validate_frontend_schedule_yaml(output.read_text(), 1_000_000)
    assert validation.valid, validation.render()


@pytest.mark.parametrize(
    "command",
    ["pip install pyyaml", "python3 -m pip install pyyaml", "uv pip install PyYAML", "pip3 -q install PyYAML"],
)
def test_yaml_generator_grader_rejects_installation_attempt_even_before_completion(command):
    event = {"kind": "tool_start", "name": "bash", "arguments": json.dumps({"command": command})}
    checks = _check_yaml_generator([event])
    assert not next(check for check in checks if "installation" in check.description).passed


@pytest.mark.parametrize("ok", [True, False])
def test_yaml_generator_grader_requires_successful_execution(ok):
    event = {
        "kind": "tool",
        "name": "bash",
        "ok": ok,
        "arguments": json.dumps({"command": "python3 /tmp/generate_schedule.py"}),
        "result": "Generated Minimal March schedule from attachment",
    }
    assert all(check.passed for check in _check_yaml_generator([event])) == ok
    assert not all(check.passed for check in _check_yaml_generator([]))


def test_generator_bytes_are_bound_to_evidence_fingerprint(monkeypatch):
    from .ai_eval import attachment_fixtures

    case = next(case for case in load_cases(CASES) if case.id == "tool-yaml-generator-repair")
    original = case_digest(case)
    filename, media_type, build = attachment_fixtures._FIXTURES["pyyaml-generator"]
    content = build()
    monkeypatch.setitem(
        attachment_fixtures._FIXTURES, "pyyaml-generator", (filename, media_type, lambda: content + b"# Changed\n")
    )
    assert case_digest(case) != original


@pytest.mark.parametrize("name", ["pyyaml-generator", "timeout-checkpoint"])
def test_text_attachment_fixtures_normalize_checkout_line_endings(name, tmp_path: Path, monkeypatch):
    from .ai_eval import attachment_fixtures

    original = load_attachment_fixtures([name])[0]
    case = next(case for case in load_cases(CASES) if name in case.attachments)
    original_digest = case_digest(case)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / f"{name}.txt").write_bytes(original.data.replace(b"\n", b"\r\n"))
    monkeypatch.setattr(attachment_fixtures, "__file__", str(tmp_path / "attachment_fixtures.py"))

    assert load_attachment_fixtures([name])[0] == original
    assert case_digest(case) == original_digest
