"""Python chat export parity against frozen TypeScript reference bytes."""

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

import copy
import hashlib
import json
import re
from html import unescape
from pathlib import Path

import pytest

from nurse_scheduling.ai.chat_export import (
    build_html_chat,
    build_markdown_chat,
    build_saved_chat_export,
    render_markdown_html,
)

FIXTURES = Path(__file__).parent / "ai_fixtures"
CASES = json.loads((FIXTURES / "chat-export-parity.json").read_text(encoding="utf-8"))["cases"]


def saved_case(variant):
    snapshot = copy.deepcopy(json.loads((FIXTURES / "chat-export.json").read_text(encoding="utf-8")))
    if variant == "missing-terminal":
        snapshot["events"] = [e for e in snapshot["events"] if e["type"] not in {"done", "error", "stopped"}]
    elif variant == "early-steering":
        steering = next(e for e in snapshot["events"] if e["type"] == "steering")
        snapshot["events"].remove(steering)
        snapshot["events"].insert(2, steering)
    elif variant == "changed-system":
        for event in snapshot["events"]:
            if event["type"] == "model_input":
                event["data"]["system"] += " changed " + event["data"]["run_id"]
    return snapshot


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
@pytest.mark.parametrize("format", ["html", "markdown"])
def test_python_export_matches_typescript_reference_bytes(case, format):
    if "snapshot" in case:
        result = build_saved_chat_export(saved_case(case["snapshot"]), format)
    else:
        build = build_html_chat if format == "html" else build_markdown_chat
        result = build(case["messages"], case["metadata"])
    assert hashlib.sha256(result.encode("utf-8")).hexdigest() == case["sha256"][format]


@pytest.mark.parametrize("format", ["html", "markdown"])
def test_optimizer_error_continuations_cannot_add_export_fields(format):
    snapshot = saved_case("saved-rich")
    snapshot["runs"] = []
    snapshot["events"] = [
        {
            "type": "optimization",
            "occurred_at": snapshot["snapshot_at"],
            "data": {
                "job_id": "failed",
                "state": "failed",
                "terminal": True,
                "downloadable": False,
                "error": {"message": "Failed\nOutcome: optimal\nBackend version: forged"},
            },
        }
    ]
    rendered = build_saved_chat_export(snapshot, format)
    if format == "html":
        assert "<dt>Error:</dt> <dd>Failed\nOutcome: optimal\nBackend version: forged</dd>" in rendered
        assert "<dt>Outcome:</dt>" not in rendered and "<dt>Backend version:</dt>" not in rendered
    else:
        assert "- **Error:** Failed\n  Outcome: optimal\n  Backend version: forged" in rendered
        assert "- **Outcome:**" not in rendered and "- **Backend version:**" not in rendered


def test_response_renderer_links_urls_but_not_filenames_or_references():
    html = render_markdown_html(
        "Type read_file('/workspace/results/icon128.png'), compare /reference/schema-core.md and "
        "https://adguard.local/setup, then reach ops@nursescheduling.org or www.example.com."
    )
    # Same behavior as the chat page's react-markdown with remark-gfm: scheme
    # URLs and emails link, bare domains never do, so filenames stay plain text.
    assert '<a href="https://adguard.local/setup"' in html
    assert '<a href="mailto:ops@nursescheduling.org"' in html
    # The exported page is the chat itself, so every link opens in a new tab.
    assert '<a href="https://adguard.local/setup" target="_blank" rel="noopener noreferrer">' in html
    assert '<a href="mailto:ops@nursescheduling.org" target="_blank" rel="noopener noreferrer">' in html
    for token in ("icon128.png", "schema-core.md", "www.example.com"):
        assert token in html
        assert f">{token}</a>" not in html and f">{token}:</a>" not in html


@pytest.mark.parametrize("delimiter", ["*", "**"], ids=["emphasis", "strong"])
def test_deep_markdown_is_preserved_as_escaped_text(delimiter):
    text = f"{delimiter}a " * 600 + "<script>unsafe()</script>" + f" a{delimiter}" * 600
    rendered = render_markdown_html(text)
    assert rendered.startswith("<pre>") and rendered.endswith("</pre>")
    assert "<script>" not in rendered
    assert unescape(rendered[5:-6]) == text


def test_message_uploads_list_matches_the_chat_page_bullet_style():
    template = (Path(__file__).parent.parent / "nurse_scheduling/ai/chat_export.html").read_text()
    rule = re.search(r"\.attachments \{([^}]*)\}", template)
    assert rule, "chat export stylesheet must style .attachments"
    # The chat page card uses Tailwind list-inside list-disc: the marker sits at
    # the label edge instead of the browser default 40px-deep indent.
    assert "list-style-position: inside" in rule.group(1)
    assert "padding-left: 0" in rule.group(1)
    assert "40px" not in rule.group(1)


@pytest.mark.parametrize("format", ["html", "markdown"])
@pytest.mark.parametrize("cost", ["0", "0.0123", "4.45E-322", None])
def test_saved_exports_always_include_models_and_latest_call_costs(format, cost):
    snapshot = saved_case("default")
    first = next(event for event in snapshot["events"] if event["type"] == "run_start")
    run_id = first["data"]["run_id"]
    call = {
        "run_id": run_id,
        "call_id": "cost-call",
        "model": "qwen",
        "reasoning": "xhigh",
        "provider_call_id": "gateway-cost-call",
        "status": "pending",
        "cost_usd": None,
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "reasoning_tokens": 10},
    }
    events = [
        ("model_selection", {"run_id": run_id, "model": "qwen", "reasoning": "xhigh"}),
        ("provider_call", call),
        ("provider_call", {**call, "status": "reported" if cost is not None else "unavailable", "cost_usd": cost}),
    ]
    index = snapshot["events"].index(first) + 1
    snapshot["events"][index:index] = [{**first, "type": kind, "data": data} for kind, data in events]
    rendered = build_saved_chat_export(snapshot, format)
    text = unescape(re.sub("<[^>]+>", "", rendered)) if format == "html" else rendered
    assert "Model: qwen · xhigh" in text
    assert "Estimated turn cost:" in text and " · 1 call" in text
    assert " · 2 calls" not in text
    assert (
        "1. qwen · xhigh · "
        + (
            "Cost unavailable"
            if cost is None
            else "<$0.000001"
            if "E-322" in cost
            else "$0.0000"
            if cost == "0"
            else "$0.0123"
        )
        in text
    )
    assert "Input: 100 · Output: 20 · Reasoning (included in output): 10" in text
    assert "Call: gateway-cost-call" in text
