"""Render saved AI conversations as HTML and Markdown in Python."""

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

# This file is mostly AI generated.

import json
import math
import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from .chat_projection import project_saved_chat


def escape_html(value: str, *, react: bool = False) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;" if react else "&#39;")
    )


def _iso(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _fixed(value: float, places: int) -> str:
    return str(Decimal.from_float(value).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))


def _count(text: str) -> str:
    count = len(text.encode("utf-16-le")) // 2
    return _fixed(count / 1000, 1) + "k" if count >= 1000 else str(count)


def _duration(start, end) -> str:
    seconds = max(0, end - start) / 1000
    if seconds < 1:
        return "<1s"
    if seconds < 10:
        return _fixed(seconds, 1) + "s"
    total = math.floor(seconds + 0.5)
    return f"{total}s" if total < 60 else f"{total // 60}m {total % 60}s"


@lru_cache(maxsize=1)
def _markdown():
    parser = MarkdownIt("gfm-like2", {"html": True, "alerts": False})
    # Parse unsafe links as links, then apply react-markdown's protocol allowlist.
    parser.validateLink = lambda _url: True
    # Match react-markdown with remark-gfm: autolink scheme URLs and emails only.
    # Bare domains would swallow filenames and doc paths (icon128.png, get-started.md).
    parser.linkify.set({"fuzzy_link": False})
    return parser


def _render_node(node) -> str:
    kind = node.type
    children = node.children or []
    render = lambda separator="": separator.join(_render_node(child) for child in children)
    if node.is_root:
        return render("\n")
    if kind == "text":
        return escape_html(node.content, react=True)
    if kind in {"html_inline", "html_block"}:
        return ""
    if kind == "inline":
        return render()
    if kind == "softbreak":
        return "\n"
    if kind == "hardbreak":
        return "<br/>\n"
    if kind == "hr":
        return "<hr/>"
    if kind == "code_inline":
        return "<code>" + escape_html(node.content, react=True) + "</code>"
    if kind in {"fence", "code_block"}:
        language = node.info.split()[0] if node.info.strip() else ""
        attribute = f' class="language-{escape_html(language, react=True)}"' if language else ""
        return f"<pre><code{attribute}>" + escape_html(node.content, react=True) + "</code></pre>"
    if kind == "image":
        alt = "".join(
            item.content if item.type in {"text", "code_inline"} else "" for item in node.walk(include_self=False)
        )
        return (
            '<span class="remote-image-omitted">[Remote image omitted'
            + (": " + escape_html(alt, react=True) if alt else "")
            + "]</span>"
        )
    if kind == "link":
        href = node.attrGet("href") or ""
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.IGNORECASE) and not re.match(
            r"^(https?|ircs?|mailto|xmpp):", href, re.IGNORECASE
        ):
            href = ""
        # The exported page is the chat itself, so every link opens in a new tab.
        return f'<a href="{escape_html(href, react=True)}" target="_blank" rel="noopener noreferrer">' + render() + "</a>"
    if kind == "paragraph" and node.hidden:
        return render()
    tag = "del" if kind == "s" else node.tag
    attrs = ""
    for name, value in node.attrs.items():
        attrs += f' {name}="{escape_html(str(value), react=True)}"'
    if kind in {"bullet_list", "ordered_list", "blockquote"}:
        body = "\n" + render("\n") + "\n"
    elif kind == "list_item":
        body = render("\n")
        if children and not children[0].hidden:
            body = "\n" + body + "\n"
        elif children and children[-1].type in {"bullet_list", "ordered_list"}:
            body += "\n"
        if "checked" in node.meta:
            checkbox = '<input type="checkbox" disabled=""' + (' checked=""' if node.meta["checked"] else "") + "/> "
            if children and not children[0].hidden:
                body = body.replace("<p>", "<p>" + checkbox, 1)
            else:
                body = checkbox + body
    else:
        body = render()
    return f"<{tag}{attrs}>{body}</{tag}>"


def render_markdown_html(text: str) -> str:
    return _render_node(SyntaxTreeNode(_markdown().parse(text or "[No message text]")))


def _summary(entry):
    kind = entry["kind"]
    if kind == "reasoning":
        return "Reasoning · " + _count(entry["text"]) + " characters"
    if kind == "schedule-change":
        return "schedule edit"
    if kind == "schedule-check":
        return "Schedule check passed" if entry["ok"] else "Schedule check failed"
    if kind == "schedule-applied":
        return "Applied to your schedule"
    state = entry.get("state")
    suffix = state if state in {"running", "interrupted"} else "failed" if not entry["ok"] else ""
    return entry["name"] + (" · " + suffix if suffix else "")


def _activity_label(entry):
    kind = entry["kind"]
    if kind in {"reasoning", "response", "schedule-change"}:
        return {"reasoning": "Reasoning", "response": "Response", "schedule-change": "Schedule change"}[kind]
    if kind in {"schedule-check", "schedule-applied"}:
        return _summary(entry)
    state = entry.get("state")
    suffix = state if state in {"running", "interrupted"} else "failed" if not entry["ok"] else ""
    return entry["name"] + (f" ({suffix})" if suffix else "")


def _activity_text(entry):
    kind = entry["kind"]
    if kind == "schedule-applied" and entry.get("notice"):
        return entry["notice"] + "\n\n" + entry["text"]
    if kind == "schedule-change":
        return f"Before:\n{entry['before']}\n\nAfter:\n{entry['after']}"
    if kind == "tool":
        return "\n\n".join(
            label + ":\n" + entry[key]
            for label, key in (("Arguments", "arguments"), ("Result", "result"))
            if entry.get(key)
        )
    return entry["text"]


def _activity_html(entry):
    kind = entry["kind"]
    if kind in {"reasoning", "schedule-check", "schedule-applied"}:
        body = '<pre class="activity-output">' + escape_html(_activity_text(entry)) + "</pre>"
    elif kind == "schedule-change":
        before, after = entry["before"].split("\n"), entry["after"].split("\n")
        prefix = 0
        while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(before), len(after)) - prefix and before[-suffix - 1] == after[-suffix - 1]:
            suffix += 1
        removed = before[prefix : len(before) - suffix]
        added = after[prefix : len(after) - suffix]
        body = (
            '<pre class="schedule-diff">'
            + "".join(
                f'<span class="{css}">{sign} {escape_html(line)}</span>'
                for css, sign, lines in (("removed", "-", removed), ("added", "+", added))
                for line in lines
            )
            + "</pre>"
        )
    else:
        arguments = (
            '<pre class="activity-output">' + escape_html(entry["arguments"]) + "</pre>"
            if entry.get("arguments") and entry["arguments"] != "{}"
            else ""
        )
        result = (
            '<pre class="activity-output">' + escape_html(entry["result"]) + "</pre>" if entry.get("result") else ""
        )
        interrupted = (
            '<p class="interrupted">The command did not return before the turn ended.</p>'
            if entry.get("state") == "interrupted" and not entry.get("result")
            else ""
        )
        body = '<div class="tool-body">' + arguments + result + interrupted + "</div>"
    return f"""<details class="activity-details">
            <summary>{escape_html(_summary(entry))}</summary>
            <div class="activity-body">{body}</div>
          </details>"""


def _timeline(message, *, html=False):
    entries = message.get("activity", [])
    if any(entry["kind"] == "response" for entry in entries):
        return entries
    if html and not message["content"] and message.get("status") in {"pending", "failed", "stopped"}:
        return entries
    return [*entries, {"kind": "response", "text": message["content"] or "[No message text]"}]


def message_label(message):
    if message["role"] != "user":
        return message["role"].capitalize()
    source = message.get("source")
    if source == "optimizer":
        return "User · Optimizer"
    topic = " - " + message["title"] if message.get("title") else ""
    return "User · " + source.capitalize() + topic if source in {"app", "status"} else "User"


def _file_rows(files, urls=None):
    def size(count):
        value = Decimal(str(count / 1000)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return f"{value:,f}".rstrip("0").rstrip(".") if value % 1 else f"{int(value):,}"

    # `urls` maps filenames to bundled attachment paths when the export carries files.
    return [
        {"label": f"{file['filename']} ({size(file['bytes'])} KB)", "url": (urls or {}).get(file["filename"])}
        for file in files
    ]


def _file_markdown(row):
    if not row["url"]:
        return row["label"]
    # Escape labels so filenames cannot add Markdown links or formatting.
    label = re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", row["label"])
    return f"[{label}]({row['url']})"


def _file_html(row):
    label = escape_html(row["label"], react=True)
    if not row["url"]:
        return label
    return f'<a href="{escape_html(row["url"], react=True)}" target="_blank" rel="noopener noreferrer">{label}</a>'


def _message_files(message, urls=None):
    if message.get("source") != "app" or message.get("title") != "Files Uploaded":
        return []
    try:
        files = json.loads(message["content"].split(": ", 1)[1])
        if not isinstance(files, list) or not all(
            isinstance(file, dict)
            and isinstance(file.get("filename"), str)
            and isinstance(file.get("bytes"), int | float)
            and file["bytes"] >= 0
            for file in files
        ):
            return []
        return _file_rows(files, urls)
    except (ValueError, IndexError):
        return []


_DETAIL_LABELS = {
    "Outcome",
    "Final score",
    "Solver",
    "Solver status",
    "Termination reason",
    "Solver timeout",
    "Backend URL",
    "Backend version",
    "API version",
    "Service",
    "Deployment",
    "Instance",
    "Backend request timeout",
    "Claimed performance",
    "Error code",
    "Error",
}


def _optimizer_parts(content):
    summary, details = [], []
    for line in content.split("\n"):
        label, separator, value = line.partition(": ")
        if separator and label in _DETAIL_LABELS:
            details.append([label, value])
        elif details:
            details[-1][1] += "\n" + (line.removeprefix(" "))
        else:
            summary.append(line)
    return "\n".join(summary), details


_RUNNING_NOTE = "An optimization was still running when this chat was exported. Its result is not included."


def _running_details(running):
    lines = [f"Job: {running['jobId']}", f"State: {running['state']}"]
    if running.get("solver"):
        lines.append("Solver: " + running["solver"])
    if running.get("timeoutSeconds") is not None:
        lines.append(f"Solver timeout: {_number(running['timeoutSeconds'])}s")
    return lines


def build_markdown_chat(messages, metadata):
    lines = [
        "# Schedule AI Chat",
        "",
        "- Exported: " + _iso(metadata["exportedAt"]),
        "- Frontend version: " + metadata["frontendVersion"],
        "- Backend version: " + metadata.get("backendVersion", "unknown"),
        "- AI server: " + metadata["endpoint"],
    ]
    urls = metadata.get("fileUrls", {})
    for message in messages:
        lines += ["", "## " + message_label(message)]
        files = _message_files(message, urls)
        if files:
            lines += ["", *["- " + _file_markdown(file) for file in files]]
        if message["role"] == "optimizer":
            summary, details = _optimizer_parts(message["content"])
            lines += ["", summary or "[No message text]"]
            if details:
                lines += ["", *[f"- **{label}:** " + value.replace("\n", "\n  ") for label, value in details]]
        elif message["role"] == "system" or message.get("source"):
            fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", message["content"])), default=0))
            lines += ["", fence + "text", message["content"], fence]
        elif message["role"] == "user":
            lines += ["", message["content"] or "[No message text]"]
        else:
            for entry in _timeline(message):
                if entry["kind"] == "response":
                    lines += ["", entry["text"] or "[No message text]"]
                else:
                    lines += ["", "### " + _activity_label(entry), "", "```text", _activity_text(entry), "```"]
        details = []
        if "createdAt" in message:
            details.append("Sent: " + _iso(message["createdAt"]))
        status = message.get("status")
        if status in {"failed", "pending", "stopped"}:
            details.append("Status: " + status)
            if status == "failed" and message.get("failureReason"):
                details.append("Error: " + message["failureReason"].replace("\n", "\n  "))
        if "responseCompletedAt" in message:
            details.append("Completed: " + _iso(message["responseCompletedAt"]))
            if "responseStartedAt" in message:
                details.append(
                    "Response time: "
                    + _number(max(0, message["responseCompletedAt"] - message["responseStartedAt"]) / 1000)
                    + "s"
                )
        if details:
            lines += ["", *["- " + detail for detail in details]]
    if files := metadata.get("uploadedFiles"):
        rows = _file_rows(files, urls)
        lines += ["", "## Uploaded files", "", *["- " + _file_markdown(row) for row in rows]]
    if running := metadata.get("runningOptimization"):
        lines += [
            "",
            "## Optimization running",
            "",
            _RUNNING_NOTE,
            "",
            *["- " + line for line in _running_details(running)],
        ]
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def _template():
    return Environment(undefined=StrictUndefined, keep_trailing_newline=True).from_string(
        Path(__file__).with_name("chat_export.html").read_text(encoding="utf-8")
    )


def build_html_chat(messages, metadata):
    rendered, urls = [], metadata.get("fileUrls", {})
    for message in messages:
        role = message["role"]
        source = " " + message["source"] if message.get("source") else ""
        files = _message_files(message, urls)
        uploads = (
            '<ul class="attachments">'
            + "".join("<li>" + _file_html(file) + "</li>" for file in files)
            + "</ul>"
            if files
            else ""
        )
        if role == "assistant":
            entries, fragments = _timeline(message, html=True), []
            for index, entry in enumerate(entries):
                separator = (
                    '<hr class="activity-separator">'
                    if index > 0 and (entry["kind"] == "response" or entries[index - 1]["kind"] == "response")
                    else ""
                )
                content = (
                    '<div class="content">' + render_markdown_html(entry["text"]) + "</div>"
                    if entry["kind"] == "response"
                    else _activity_html(entry)
                )
                fragments.append('<div class="activity-entry">' + separator + content + "</div>")
            timeline = (
                '<div class="assistant-activity" aria-label="Assistant activity">' + "".join(fragments) + "</div>"
            )
        elif role == "system" or message.get("source"):
            timeline = f'<details class="system-prompt"><summary>{_count(message["content"])} characters</summary><pre>{escape_html(message["content"])}</pre></details>'
        elif role == "optimizer":
            summary, details = _optimizer_parts(message["content"])
            rows = "".join(
                f"<div><dt>{escape_html(label)}:</dt> <dd>{escape_html(value)}</dd></div>" for label, value in details
            )
            timeline = (
                '<div class="content">'
                + escape_html(summary or "[No message text]")
                + "</div>"
                + ('<dl class="optimizer-details">' + rows + "</dl>" if rows else "")
            )
        else:
            timeline = '<div class="content">' + escape_html(message["content"] or "[No message text]") + "</div>"
        status, timing = "", ""
        if message.get("status") == "pending" and not message["content"]:
            status = '<p class="message-status" role="status">Thinking</p>'
        elif message.get("status") == "failed":
            reason = message.get("failureReason")
            shown = any(
                entry["kind"] == "response" and entry["text"] == reason for entry in _timeline(message, html=True)
            )
            status = (
                '<p class="failure">'
                + escape_html(reason if reason and not shown else "This response failed before completion.")
                + "</p>"
            )
        elif message.get("status") == "stopped":
            status = '<p class="message-status">Stopped before completion.</p>'
        at = message.get("responseCompletedAt", message.get("createdAt"))
        if at is not None:
            iso = _iso(at)
            display = iso.replace("T", " ").replace("Z", " UTC")
            duration = (
                " · " + _duration(message["responseStartedAt"], message["responseCompletedAt"])
                if "responseStartedAt" in message and "responseCompletedAt" in message
                else ""
            )
            timing = f'<time datetime="{iso}" title="{escape_html(display)}">{escape_html(display)}{duration}</time>'
        rendered.append(f"""
      <article class="message {role}{source}">
        <div class="label">{escape_html(message_label(message))}</div>
        {uploads}
        {timeline}
        {status}{timing}
      </article>""")
    uploads = ""
    if metadata.get("uploadedFiles"):
        uploads = (
            '\n    <section class="proposal" aria-label="Uploaded files">\n      <h2>Uploaded files</h2>\n      <ul>'
            + "".join("<li>" + _file_html(row) + "</li>" for row in _file_rows(metadata["uploadedFiles"], urls))
            + "</ul>\n    </section>"
        )
    running = ""
    if metadata.get("runningOptimization"):
        running = (
            '\n    <section class="proposal" aria-label="Optimization running">\n      <h2>Optimization running</h2>\n      <p>'
            + _RUNNING_NOTE
            + "</p>\n      <ul>"
            + "".join(
                "<li>" + escape_html(line) + "</li>" for line in _running_details(metadata["runningOptimization"])
            )
            + "</ul>\n    </section>"
        )
    return _template().render(
        exported_at=escape_html(_iso(metadata["exportedAt"])),
        frontend=escape_html(metadata["frontendVersion"]),
        backend=escape_html(metadata.get("backendVersion", "unknown")),
        endpoint=escape_html(metadata["endpoint"]),
        messages="".join(rendered),
        uploads=uploads,
        running=running,
    )


def build_saved_chat_export(snapshot: dict, format: str) -> str:
    """Render the same saved snapshot for HTTP and command-line exports."""
    messages, metadata = project_saved_chat(snapshot)
    if format == "html":
        return build_html_chat(messages, metadata)
    if format == "markdown":
        return build_markdown_chat(messages, metadata)
    raise ValueError("Choose html or markdown")
