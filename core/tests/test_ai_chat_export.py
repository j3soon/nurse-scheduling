"""Chat export regression checks, independent of live browser rendering parity."""

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
from nurse_scheduling.ai.chat_projection import project_saved_chat

FIXTURES = Path(__file__).parent / "ai_fixtures"
CASES = json.loads((FIXTURES / "chat-export-parity.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize(
    "success,aborted,skipped,state,label",
    [
        (True, False, False, "completed", "Conversation summarized"),
        (False, False, False, "failed", "Summarization failed"),
        (False, True, False, "interrupted", "Summarization interrupted"),
        (False, False, True, "skipped", "No compaction needed"),
    ],
)
@pytest.mark.parametrize("reason", ["threshold", "manual"])
def test_saved_compaction_status_matches_live_activity_and_exports(success, aborted, skipped, state, label, reason):
    snapshot = saved_case("saved-rich")
    run = snapshot["runs"][0]
    snapshot["runs"] = [run]
    data = {"run_id": run["id"], "reason": reason, "tokens_before": 25000}
    snapshot["events"] = [
        {"type": "compaction_start", "data": data, "occurred_at": snapshot["snapshot_at"]},
        {
            "type": "compaction_end",
            "data": {**data, "success": success, "aborted": aborted, "skipped": skipped},
            "occurred_at": snapshot["snapshot_at"],
        },
    ]
    messages, _ = project_saved_chat(snapshot)
    activity = messages[-1]["activity"]
    assert len(activity) == (2 if reason == "manual" else 1)
    assert activity[-1]["kind"] == "compaction" and activity[-1]["state"] == state
    for format in ("html", "markdown"):
        rendered = build_saved_chat_export(snapshot, format)
        assert label in rendered and activity[-1]["text"] in rendered
        assert rendered.count("You requested context compaction.") == (1 if reason == "manual" else 0)


def test_saved_character_progress_survives_recovery_and_matches_export_counts():
    from nurse_scheduling.ai.session_event_stream import SessionEvent, fold_recovery

    snapshot = saved_case("saved-rich")
    run = snapshot["runs"][0]
    snapshot["runs"] = [run]
    rows = [
        ("compaction_start", {"reason": "manual", "tokens_before": 10000}),
        ("generation_progress", {"kind": "compaction", "characters": 50, "step": 1}),
        (
            "compaction_end",
            {
                "reason": "manual",
                "tokens_before": 10000,
                "success": True,
                "aborted": False,
                "characters": 50,
                "step": 1,
            },
        ),
        ("compaction_start", {"reason": "threshold", "tokens_before": 10000}),
        ("generation_progress", {"kind": "compaction", "characters": 2, "step": 2}),
        (
            "compaction_end",
            {
                "reason": "threshold",
                "tokens_before": 10000,
                "success": True,
                "aborted": False,
                "characters": 2,
                "step": 2,
            },
        ),
        ("generation_progress", {"kind": "tool_calls", "characters": 90, "step": 1}),
        ("provider_retry", {"message": "Retrying"}),
        ("generation_progress", {"kind": "tool_calls", "characters": 2, "step": 1}),
        ("tool_start", {"name": "read", "arguments": "{}", "tool_call_id": "call"}),
        ("tool", {"name": "read", "arguments": "{}", "tool_call_id": "call", "result": "新😀", "ok": True}),
        ("reasoning", {"text": "新😀"}),
        ("delta", {"text": "新😀"}),
        ("done", {}),
    ]
    events = [SessionEvent(index + 1, kind, {"run_id": run["id"], **data}) for index, (kind, data) in enumerate(rows)]

    def project(events):
        snapshot["events"] = [
            {"type": event.type, "data": event.data, "occurred_at": snapshot["snapshot_at"]} for event in events
        ]
        return project_saved_chat(snapshot)[0]

    original = project(events)
    assert project(fold_recovery(events)) == original
    activity = original[-1]["activity"]
    assert [entry["characters"] for entry in activity if entry["kind"] == "compaction"] == [50, 2]
    assert not any(entry.get("state") == "preparing" for entry in activity)
    for format in ("html", "markdown"):
        rendered = build_saved_chat_export(snapshot, format)
        assert "Reasoning · 2 characters" in rendered and "50 characters" in rendered
        assert "pass 2 · 2 characters" in rendered
        assert "新😀" in rendered


def test_saved_summary_and_tool_repair_match_model_context_in_both_exports():
    snapshot = saved_case("saved-rich")
    run = snapshot["runs"][0]
    snapshot["runs"] = [run]
    data = {"run_id": run["id"]}
    snapshot["events"] = [
        {
            "type": "compaction_end",
            "data": {
                **data,
                "reason": "threshold",
                "tokens_before": 25000,
                "success": True,
                "aborted": False,
                "summary": "Keep P1 off nights.",
                "keep_messages": 4,
            },
        },
        {
            "type": "tool",
            "data": {
                **data,
                "name": "bash",
                "arguments": '{"command":',
                "result": "Not executed",
                "ok": False,
                "replay_arguments": "{}",
            },
        },
        {"type": "response_end", "data": {**data, "stop_reason": "error", "context_note": "Workspace discarded."}},
    ]
    for event in snapshot["events"]:
        event["occurred_at"] = snapshot["snapshot_at"]
    messages, _ = project_saved_chat(snapshot)
    assert messages[-1]["activity"][0]["invalidated"]
    assert messages[-1]["activity"][1]["replayArguments"] == "{}"
    for format in ("html", "markdown"):
        rendered = build_saved_chat_export(snapshot, format)
        assert "[Conversation summary]" in rendered and "Keep P1 off nights." in rendered
        assert "Omitted from future model context" in rendered
        assert "Arguments sent in later model context" in rendered


@pytest.mark.parametrize("terminal", ["error", "stopped"])
@pytest.mark.parametrize("boundary", [False, True], ids=["terminal-only", "response-boundary"])
def test_failed_steered_run_discards_summaries_on_all_replies(terminal, boundary):
    snapshot = saved_case("saved-rich")
    run = snapshot["runs"][0]
    snapshot["runs"] = [run]
    events = [
        ("run_start", {"trigger": "user"}),
        (
            "compaction_end",
            {
                "reason": "threshold",
                "tokens_before": 25000,
                "success": True,
                "aborted": False,
                "summary": "Summary from a run that later fails.",
                "keep_messages": 1,
            },
        ),
        ("delta", {"text": "Earlier completed output."}),
        ("steering", {"message_id": "steer", "message": "Now edit the schedule."}),
        ("delta", {"text": "Partial second reply."}),
        *(
            [
                (
                    "response_end",
                    {
                        "stop_reason": "error" if terminal == "error" else "aborted",
                        "context_note": "The run's summaries were discarded.",
                    },
                )
            ]
            if boundary
            else []
        ),
        (terminal, {"message": "Validation failed."} if terminal == "error" else {}),
    ]
    snapshot["events"] = [
        {"type": kind, "data": {"run_id": run["id"], **data}, "occurred_at": snapshot["snapshot_at"]}
        for kind, data in events
    ]
    messages, _ = project_saved_chat(snapshot)
    earlier, latest = [message for message in messages if message["role"] == "assistant"]
    assert earlier["activity"][0].get("invalidated") is True
    assert earlier["content"] == "Earlier completed output."
    assert earlier["status"] is None
    assert earlier["activity"][1].get("context") != "omitted"
    assert latest["status"] == ("failed" if terminal == "error" else "stopped")
    for format in ("html", "markdown"):
        rendered = build_saved_chat_export(snapshot, format)
        assert "Discarded conversation summary" in rendered
        assert "Omitted from future model context" in rendered
        assert "Summary used in future model context." not in rendered


@pytest.mark.parametrize("keep", [0, 4])
def test_export_separates_notices_and_summary_without_changing_saved_messages(keep):
    messages = [
        {
            "role": "assistant",
            "content": "Continued.",
            "activity": [
                {"kind": "tool", "name": "read", "arguments": "{}", "result": "Tool output", "ok": True},
                {"kind": "notice", "text": "You requested context compaction."},
                {
                    "kind": "compaction",
                    "reason": "manual",
                    "state": "completed",
                    "text": "The conversation was summarized.",
                    "summary": "Keep nights.",
                    "keepMessages": keep,
                },
                {"kind": "response", "text": "Continued."},
                {"kind": "notice", "text": "Sent in future model context: [App event] Workspace discarded."},
            ],
        }
    ]
    original = copy.deepcopy(messages)
    metadata = {"exportedAt": 1792919105509, "frontendVersion": "test", "endpoint": "https://ai.example"}
    html = build_html_chat(messages, metadata)
    articles = html.split('<article class="')[1:]
    assert articles[0].startswith('message assistant"') and "Tool output" in articles[0]
    assert (
        articles[1].startswith('message assistant app-notice"') and "You requested context compaction." in articles[1]
    )
    assert articles[2].startswith('message user app"') and "User · Conversation summary" in articles[2]
    assert articles[3].startswith('message assistant"') and "Continued." in articles[3]
    assert articles[4].startswith('message user app"') and "[App event] Workspace discarded." in articles[4]
    markdown = build_markdown_chat(messages, metadata)
    for rendered in (html, markdown):
        assert (
            "The latest 4 messages remain unchanged after the summary." in rendered
            if keep
            else ("The summary replaces all earlier conversation messages in model context." in rendered)
        )
        assert rendered.count("You requested context compaction.") == 1
        assert "User · Conversation summary" in rendered
        assert "[No message text]" not in rendered
        assert ("Compacted out of context." not in rendered) if keep else ("Compacted out of context." in rendered)
    assert messages == original


def test_exports_preserve_tools_without_inventing_an_html_response():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "activity": [
                {"kind": "tool", "name": "read", "arguments": "{}", "result": "First output", "ok": True},
                {"kind": "notice", "text": "Workspace changed."},
                {"kind": "tool", "name": "read", "arguments": "{}", "result": "Last output", "ok": True},
            ],
        }
    ]
    metadata = {"exportedAt": 1792919105509, "frontendVersion": "test", "endpoint": "https://ai.example"}
    html = build_html_chat(messages, metadata)
    assert "First output" in html and "Last output" in html
    assert "[No message text]" not in html
    markdown = build_markdown_chat(messages, metadata)
    assert markdown.count("[No message text]") == 1
    assert markdown.index("Last output") < markdown.index("[No message text]")


@pytest.mark.parametrize("status", [None, "failed", "stopped"])
def test_export_keeps_answer_metadata_before_a_trailing_app_notice(status):
    messages = [
        {
            "role": "assistant",
            "content": "Updated.",
            "status": status,
            "failureReason": "The provider failed.",
            "modelSelection": {"model": "test-model", "reasoning": "high"},
            "costSummary": {"usd": "0.02", "calls": 1, "pending": 0, "unavailable": 0},
            "activity": [
                {"kind": "response", "text": "Updated."},
                {"kind": "schedule-applied", "text": "The schedule was applied."},
            ],
        }
    ]
    metadata = {"exportedAt": 1792919105509, "frontendVersion": "test", "endpoint": "https://ai.example"}
    html = build_html_chat(messages, metadata)
    answer, notice = html.split('<article class="')[1:]
    assert "test-model · high" in answer and "Estimated turn cost" in answer
    assert "test-model · high" not in notice and "Estimated turn cost" not in notice
    if status:
        assert ("The provider failed." if status == "failed" else "Stopped before completion.") in answer
    markdown = build_markdown_chat(messages, metadata)
    assert markdown.index("Model: test-model") < markdown.index("## App notice")
    assert markdown.index("Estimated turn cost") < markdown.index("## App notice")


def test_manual_compaction_keeps_metadata_on_notice_before_summary():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "responseStartedAt": 1000,
            "responseCompletedAt": 2500,
            "modelSelection": {"model": "test-model", "reasoning": "high"},
            "costSummary": {"usd": "0.02", "calls": 1, "pending": 0, "unavailable": 0},
            "activity": [
                {"kind": "notice", "text": "You requested context compaction."},
                {
                    "kind": "compaction",
                    "reason": "manual",
                    "state": "completed",
                    "text": "The conversation was summarized.",
                    "summary": "Keep nights.",
                    "keepMessages": 2,
                },
            ],
        }
    ]
    original = copy.deepcopy(messages)
    metadata = {"exportedAt": 1792919105509, "frontendVersion": "test", "endpoint": "https://ai.example"}
    notice, summary = build_html_chat(messages, metadata).split('<article class="')[1:]
    assert notice.startswith('message assistant app-notice"')
    for detail in ("test-model · high", "Estimated turn cost", "1970-01-01T00:00:02.500Z", "1.5s"):
        assert detail in notice and detail not in summary
    markdown = build_markdown_chat(messages, metadata)
    for detail in ("Model: test-model", "Estimated turn cost", "Completed:", "Response time: 1.5s"):
        assert markdown.index(detail) < markdown.index("## User · Conversation summary")
    assert messages == original


def test_export_counts_parallel_tools_and_omits_uncommitted_or_failed_split_turns():
    reason = "The AI provider failed (HTTP 525)."
    messages = [
        {"role": "user", "content": "Compacted question"},
        {
            "role": "assistant",
            "content": "Compacted answer",
            "activity": [{"kind": "response", "text": "Compacted answer"}],
        },
        {"role": "user", "content": "Retained question"},
        {
            "role": "assistant",
            "content": "Retained answer",
            "activity": [
                {"kind": "reasoning", "text": "Checking both files."},
                {"kind": "tool", "name": "read", "arguments": '{"path":"a"}', "result": "A", "ok": True},
                {"kind": "tool", "name": "read", "arguments": '{"path":"b"}', "result": "B", "ok": True},
                {"kind": "response", "text": "Retained answer"},
            ],
        },
        {"role": "user", "content": "Stale question"},
        {
            "role": "assistant",
            "content": "This response was not saved.",
            "status": "failed",
            "activity": [{"kind": "response", "text": "This response was not saved."}],
        },
        {"role": "user", "content": "Unsent question"},
        {
            "role": "assistant",
            "content": "Upload failed.",
            "status": "failed",
            "failureReason": "Upload failed.",
            "unsentFiles": ["ward.xlsx"],
        },
        {"role": "user", "content": "Interrupted question"},
        {
            "role": "assistant",
            "content": reason,
            "status": "failed",
            "failureReason": reason,
            "activity": [
                {"kind": "notice", "text": "Sent in future model context: [App event] Workspace discarded."},
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "activity": [
                {"kind": "notice", "text": "You requested context compaction."},
                {
                    "kind": "compaction",
                    "reason": "manual",
                    "state": "completed",
                    "text": "The conversation was summarized.",
                    "summary": "Summary text.",
                    "keepMessages": 7,
                },
            ],
        },
    ]
    metadata = {"exportedAt": 1792919105509, "frontendVersion": "test", "endpoint": "https://ai.example"}
    html = build_html_chat(messages, metadata)
    assert f'<p class="failure-reason">{reason}</p>' in html
    assert f"{len(reason)} characters" not in html
    articles = html.split('<article class="')[1:]
    by_text = lambda text: next(article for article in articles if text in article)
    assert "Compacted out of context." in by_text("Compacted question")
    assert "Compacted out of context." in by_text("Compacted answer")
    for text in ("Retained question", "Retained answer", "Stale question", "Unsent question", "Interrupted question"):
        assert "Compacted out of context." not in by_text(text)
    markdown = build_markdown_chat(messages, metadata)
    assert markdown.count("Compacted out of context.") == 2
    assert f"- Error: {reason}" in markdown


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
def test_export_matches_frozen_reference_bytes(case, format):
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
        assert re.search(
            r"<dt[^>]*>Error:</dt> <dd[^>]*>Failed\nOutcome: optimal\nBackend version: forged</dd>", rendered
        )
        assert not re.search(r"<dt[^>]*>(Outcome|Backend version):</dt>", rendered)
    else:
        assert "- **Error:** Failed\n  Outcome: optimal\n  Backend version: forged" in rendered
        assert "- **Outcome:**" not in rendered and "- **Backend version:**" not in rendered


def test_saved_activity_keeps_the_live_view_model_input_and_app_notice_labels():
    snapshot = saved_case("default")
    run_id = next(event for event in snapshot["events"] if event["type"] == "run_start")["data"]["run_id"]
    index = next(i for i, event in enumerate(snapshot["events"]) if event["type"] == "tool")
    retry = {**snapshot["events"][index], "type": "provider_retry", "data": {"run_id": run_id, "message": "Retrying."}}
    snapshot["events"].insert(index, retry)
    html = build_saved_chat_export(snapshot, "html")
    markdown = build_saved_chat_export(snapshot, "markdown")
    # A provider retry notice is an app notice in both formats.
    assert '<div class="activity-entry app-notice"><p class="notice-message" role="status">Retrying.</p></div>' in html
    assert "### App notice\n\n```text\nRetrying.\n```" in markdown
    assert '<div class="activity-entry model-input">' in html
    assert '<p class="activity-status">Validation result sent to AI.</p>' in html
    assert '<p class="activity-status">Not sent to AI.</p>' in html
    assert "Sent to AI." not in html


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
    template = (Path(__file__).parent.parent / "nurse_scheduling/ai/chat_styles.css").read_text(encoding="utf-8")
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
    assert ("qwen · xhigh" if format == "html" else "Model: qwen · xhigh") in text
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
