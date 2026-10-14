"""Check trace extraction against export roles, outcomes and nested content."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# This test is mostly AI generated.

import contextlib
import html
import io
import json
import tempfile
import unittest
from pathlib import Path

from extract_html_traces import extract_export, main


def message(role, body):
    return f'<article class="message {role}"><div class="label">{role}</div>{body}</article>'


def tool(summary, *outputs):
    body = "".join(
        f'<pre class="activity-output">{html.escape(output)}</pre>'
        for output in outputs
    )
    return f'<div class="activity-entry"><details class="activity-details"><summary>{summary}</summary><div class="tool-body">{body}</div></details></div>'


class ExtractHtmlTracesTests(unittest.TestCase):
    def test_collapsed_app_and_status_text_is_content_not_system_policy(self):
        source = message("system", '<details class="system-prompt"><pre>Policy</pre></details>')
        for origin in ("app", "status", "optimizer"):
            source += message(
                f"user {origin}",
                f'<details class="system-prompt"><summary>Hidden text</summary><pre>{origin} context</pre></details>',
            )
        messages = extract_export(source)["messages"]
        self.assertEqual(messages[0]["system_prompts"], ["Policy"])
        for entry, origin in zip(messages[1:], ("app", "status", "optimizer"), strict=True):
            self.assertEqual(entry["content"], [f"{origin} context"])
            self.assertEqual(entry["system_prompts"], [])

    def test_roles_timestamps_and_pending_state_survive(self):
        source = message(
            "user app",
            '<details class="system-prompt"><summary>8 characters</summary><pre>  saved\n</pre></details>',
        )
        source += message(
            "assistant",
            '<div class="content"><p>First paragraph.</p><p>Next<br>line.</p></div><time datetime="2026-01-01T00:00:00Z" title="UTC">00:00</time><p class="failure">Not saved.</p>',
        )
        source += '<section class="proposal" aria-label="Pending proposal"><pre>+ pending</pre></section>'
        source += '<section class="proposal" aria-label="Uploaded files"><p>input.xlsx (1 KB)</p></section>'
        report = extract_export(source)
        self.assertEqual(report["messages"][0]["role"], "user")
        self.assertEqual(report["messages"][0]["sources"], ["app"])
        self.assertEqual(report["messages"][0]["content"], ["  saved\n"])
        self.assertEqual(report["messages"][0]["system_prompts"], [])
        assistant = report["messages"][1]
        self.assertEqual(assistant["content"], ["First paragraph.\nNext\nline."])
        self.assertEqual(assistant["timing"][0]["datetime"], "2026-01-01T00:00:00Z")
        self.assertEqual(report["inventory"]["failed_assistant_turns"], 1)
        self.assertEqual(
            [s["label"] for s in report["sections"]],
            ["Pending proposal", "Uploaded files"],
        )

    def test_counts_use_exported_states_not_result_keywords(self):
        source = message(
            "assistant",
            tool("bash", '{"command":"check"}', "Error: detected intentionally\n")
            + tool("read · failed", "missing")
            + tool("optimizer · interrupted")
            + tool("bash · running"),
        )
        inventory = extract_export(source)["inventory"]
        self.assertEqual(inventory["tool_calls"], 4)
        self.assertEqual(inventory["tools"], {"bash": 2, "optimizer": 1, "read": 1})
        self.assertEqual(inventory["failed_tool_calls"], 1)
        self.assertEqual(inventory["interrupted_tool_calls"], 1)

    def test_reasoning_response_and_schedule_preview_are_not_tools(self):
        activity = '<div class="activity-entry"><details class="activity-details"><summary>Reasoning · 6 characters</summary><pre class="activity-output">secret</pre></details></div>'
        activity += (
            '<div class="activity-entry"><div class="content">Reply.</div></div>'
        )
        activity += '<div class="activity-entry"><details class="activity-details"><summary>schedule edit</summary><pre class="schedule-diff">+ change</pre></details></div>'
        source = message("assistant", activity)
        report = extract_export(source)
        self.assertEqual(report["inventory"]["tool_calls"], 0)
        self.assertEqual(report["inventory"]["reasoning_entries"], 1)
        self.assertNotIn("secret", json.dumps(report))
        self.assertEqual(
            [a["index"] for a in report["messages"][0]["activity"]], [1, 2]
        )
        included = extract_export(source, include_reasoning=True)
        self.assertEqual(included["messages"][0]["activity"][0]["outputs"], ["secret"])

    def test_encoded_earlier_chat_and_scripts_do_not_add_messages(self):
        old_chat = message("assistant", tool("bash · failed", "old result"))
        script = '<script>throw new Error("Do not execute");' + old_chat + "</script>"
        source = script + message("assistant", tool("read", old_chat))
        report = extract_export(source)
        self.assertEqual(report["inventory"]["messages"], 1)
        self.assertEqual(report["inventory"]["tool_calls"], 1)
        self.assertEqual(report["inventory"]["failed_tool_calls"], 0)
        self.assertEqual(report["messages"][0]["activity"][0]["outputs"], [old_chat])

    def test_preformatted_arguments_and_results_keep_whitespace(self):
        arguments = '  {"command": "echo a & b"}\n'
        result = "first\n  second <tag>\n"
        report = extract_export(message("assistant", tool("bash", arguments, result)))
        self.assertEqual(
            report["messages"][0]["activity"][0]["outputs"], [arguments, result]
        )

    def test_cli_sorts_deduplicates_and_saves_only_requested_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = [root / name for name in ["b.html", "a.html"]]
            for source in sources:
                source.write_text(
                    message("user", '<div class="content">Question.</div>'),
                    encoding="utf-8",
                )
            with contextlib.redirect_stdout(io.StringIO()) as output:
                main(
                    [
                        str(sources[0]),
                        str(sources[1]),
                        str(sources[0]),
                        "--output-dir",
                        str(root / "reports"),
                    ]
                )
            lines = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(
                [Path(line["source"]).name for line in lines], ["a.html", "b.html"]
            )
            inventory = json.loads((root / "reports/inventory.json").read_text())
            self.assertEqual(inventory, lines)
            self.assertEqual(len(list((root / "reports").glob("trace-*.json"))), 2)
            self.assertNotIn("Question.", output.getvalue())

    def test_unrelated_html_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "No Schedule AI Chat"):
            extract_export("<html><p>Not an export.</p></html>")


if __name__ == "__main__":
    unittest.main()
