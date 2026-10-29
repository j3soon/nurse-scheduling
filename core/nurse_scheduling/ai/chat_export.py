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

MAX_MARKDOWN_DEPTH = 64


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
    return f"{len(text):,}"


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
        return (
            f'<div class="code-container"><pre class="code-block"><code{attribute}>'
            + escape_html(node.content, react=True)
            + "</code></pre></div>"
        )
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
        return (
            f'<a href="{escape_html(href, react=True)}" target="_blank" rel="noopener noreferrer">' + render() + "</a>"
        )
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
    result = f"<{tag}{attrs}>{body}</{tag}>"
    return '<div class="table-container">' + result + "</div>" if kind == "table" else result


def render_markdown_html(text: str) -> str:
    text = text or "[No message text]"
    tokens = _markdown().parse(text)
    # Inline emphasis can exceed the parser's nesting limit. Check flat tokens before
    # constructing the syntax tree, because its constructor and renderer both recurse.
    pending = [(tokens, 0)]
    while pending:
        children, depth = pending.pop()
        for token in children:
            level = depth + token.level
            if level > MAX_MARKDOWN_DEPTH:
                return "<pre>" + escape_html(text, react=True) + "</pre>"
            if token.children:
                pending.append((token.children, level + 1))
    return _render_node(SyntaxTreeNode(tokens))


def _summary(entry):
    kind = entry["kind"]
    if kind == "reasoning":
        return "Reasoning · " + _count(entry["text"]) + " characters"
    if kind == "schedule-change":
        return "schedule edit"
    if kind == "compaction":
        if entry.get("invalidated"):
            return "Conversation summary discarded"
        label = {
            "running": "Summarizing conversation",
            "completed": "Conversation summarized",
            "failed": "Summarization failed",
            "interrupted": "Summarization interrupted",
            "skipped": "No compaction needed",
        }[entry["state"]]
        if "characters" in entry:
            if entry.get("step", 1) > 1:
                label += f" · pass {entry['step']}"
            label += f" · {entry['characters']:,} characters"
        return label
    if kind == "schedule-check":
        return "Schedule check passed" if entry["ok"] else "Schedule check failed"
    if kind == "schedule-applied":
        return "Applied to your schedule"
    if kind == "notice":
        return "App notice"
    state = entry.get("state")
    if "argumentsCharacters" in entry:
        label = "Preparing tool calls" if state == "preparing" else f"{entry['name']} · {state}"
        return label + f" · {entry['argumentsCharacters']:,} characters"
    suffix = state if state in {"running", "interrupted"} else "failed" if not entry["ok"] else ""
    return entry["name"] + (" · " + suffix if suffix else "")


def _activity_label(entry):
    kind = entry["kind"]
    if kind == "reasoning":
        return _summary(entry)
    if kind in {"reasoning", "response", "schedule-change"}:
        return {"reasoning": "Reasoning", "response": "Response", "schedule-change": "Schedule change"}[kind]
    if kind in {"notice", "schedule-check", "schedule-applied", "compaction"}:
        return _summary(entry)
    state = entry.get("state")
    if "argumentsCharacters" in entry:
        return _summary(entry)
    suffix = state if state in {"running", "interrupted"} else "failed" if not entry["ok"] else ""
    return entry["name"] + (f" ({suffix})" if suffix else "")


def _compaction_summary_text(entry):
    if entry.get("invalidated"):
        status = "Omitted from future model context because this run failed."
    else:
        keep = entry.get("keepMessages", 0)
        status = "The app supplies this summary to AI using the user role.\n" + (
            f"The latest {keep} messages remain unchanged after the summary."
            if keep
            else "The summary replaces all earlier conversation messages in model context."
        )
    return f"{status}\n\n[Conversation summary]\n{entry['summary']}"


def _activity_text(entry):
    kind = entry["kind"]
    if kind == "compaction" and "summary" in entry:
        return entry["text"] + "\n" + _compaction_summary_text(entry)
    if kind in {"response", "reasoning"} and entry.get("context") == "omitted":
        return "Incomplete response. Omitted from future model context.\n\n" + entry["text"]
    if kind == "schedule-applied" and entry.get("notice"):
        return entry["notice"] + "\n\n" + entry["text"]
    if kind == "schedule-change":
        return f"Before:\n{entry['before']}\n\nAfter:\n{entry['after']}"
    if kind == "tool":
        text = "\n\n".join(
            label + " (" + _count(entry[key]) + " characters):\n" + entry[key]
            for label, key in (("Arguments", "arguments"), ("Result", "result"))
            if entry.get(key)
        )
        if "replayArguments" in entry:
            text += "\n\nNot executed. Arguments sent in later model context:\n" + entry["replayArguments"]
        return text
    return entry["text"]


def _chunked_text(text, label):
    chunks = [text[start : start + 2000] for start in range(0, len(text), 2000)] or [""]
    parts = ['<div><pre class="activity-output">' + escape_html(chunks[0]) + "</pre>"]
    for index, chunk in enumerate(chunks[1:], 1):
        remaining = len(text) - index * 2000
        parts.append(
            '<details class="more-output"><summary role="button">Show more '
            + label
            + f' ({remaining:,} characters left)</summary><pre class="activity-output">'
            + escape_html(chunk)
            + "</pre></details>"
        )
    return "".join(parts) + "</div>"


def _tool_section(title, text, label):
    return (
        '<section class="tool-section" aria-label="Tool '
        + label
        + '"><h3>'
        + title
        + " <span>· "
        + _count(text)
        + " characters</span></h3>"
        + _chunked_text(text, "arguments" if label == "arguments" else "output")
        + "</section>"
    )


def _activity_html(entry):
    kind = entry["kind"]
    if kind == "notice":
        return '<p class="notice-message" role="status">' + escape_html(entry["text"]) + "</p>"
    if kind == "compaction":
        body = "<p>" + escape_html(entry["text"]) + "</p>"
        if "summary" in entry:
            body += _compaction_summary_html(entry)
    elif kind in {"reasoning", "schedule-check", "schedule-applied"}:
        body = _chunked_text(entry["text"], "reasoning" if kind == "reasoning" else "details")
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
            _tool_section("Command" if entry["name"] == "bash" else "Arguments", entry["arguments"], "arguments")
            if entry.get("arguments") and entry["arguments"] != "{}"
            else ""
        )
        result = _tool_section("Result", entry["result"], "result") if entry.get("result") else ""
        interrupted = (
            '<p class="interrupted">The command did not return before the turn ended.</p>'
            if entry.get("state") == "interrupted" and not entry.get("result")
            else ""
        )
        replay = (
            '<section class="replay-arguments" aria-label="Arguments sent in model context"><p>Not executed. The original arguments above were truncated. Arguments sent in later model context:</p><pre>'
            + escape_html(entry["replayArguments"])
            + "</pre></section>"
            if "replayArguments" in entry
            else ""
        )
        body = '<div class="tool-body">' + arguments + result + interrupted + replay + "</div>"
    audience = (
        '<p class="activity-status">Validation result sent to AI.</p>'
        if kind == "schedule-check"
        else '<p class="activity-status">Not sent to AI.</p>'
        if kind == "schedule-applied"
        else ""
    )
    opened = " open" if kind == "schedule-check" and not entry["ok"] else ""
    color = (
        "activity-success"
        if kind == "schedule-applied" or (kind == "schedule-check" and entry["ok"])
        else "activity-error"
        if kind == "schedule-check"
        else "activity-muted"
    )
    return f"""<details class="activity-details {color}"{opened}>
            <summary>{escape_html(_summary(entry))}</summary>
            {audience}<div class="activity-body">{body}</div>
          </details>"""


def _timeline(message, *, html=False):
    entries = message.get("activity", [])
    if message.get("presentation") or message.get("split"):
        return entries
    if any(entry["kind"] == "response" for entry in entries):
        return entries
    if html and not message["content"]:
        return entries
    return [*entries, {"kind": "response", "text": message["content"] or "[No message text]"}]


def _append_activity_bubble(parts, base, entry, presentation=None):
    if not parts or parts[-1].get("presentation") != presentation or parts[-1]["role"] != "assistant":
        parts.append({**base, "content": "", "activity": [], "presentation": presentation})
    parts[-1]["activity"].append(entry)
    if entry["kind"] == "response":
        parts[-1]["content"] += entry["text"]


def _context_message_count(message) -> int:
    role = message["role"]
    presentation = message.get("presentation")
    if role in {"system", "optimizer"} or presentation == "notice":
        return 0
    if presentation == "summary":
        return 0 if message["compaction"].get("invalidated") else 1
    if role == "user":
        return 1
    if message.get("status") == "pending":
        return 0
    activity = message.get("activity", [])
    if not activity:
        return 0 if message.get("status") in {"failed", "stopped"} or not message.get("content") else 1
    count = 0
    step = "none"
    for entry in activity:
        kind = entry["kind"]
        if kind in {"reasoning", "response"}:
            if entry.get("context") == "omitted" or (
                message.get("status") in {"failed", "stopped"} and entry.get("context") != "complete"
            ):
                step = "none"
                continue
            if step != "text":
                count += 1
                step = "text"
        elif kind == "tool" and entry.get("state") != "preparing":
            if step == "none":
                count += 1
            count += 1
            step = "none" if entry.get("endsRound") else "tools"
    return count


def _display_messages(messages):
    """Match live bubbles without changing saved messages or model context."""
    footer_fields = {
        "createdAt",
        "responseStartedAt",
        "responseCompletedAt",
        "status",
        "failureReason",
        "truncated",
        "modelSelection",
        "providerCalls",
        "costSummary",
        "downloadId",
        "unsentFiles",
    }
    bubbles = []
    counts = []
    for message in messages:
        activity = message.get("activity", [])
        if message["role"] != "assistant" or not any(
            entry["kind"] in {"notice", "schedule-applied", "compaction"} for entry in activity
        ):
            parts = [dict(message)]
        else:
            base = {key: value for key, value in message.items() if key not in footer_fields | {"activity", "content"}}
            parts = []

            if (
                message["content"]
                and (message.get("status") != "failed" or message["content"] != message.get("failureReason"))
                and not any(entry["kind"] == "response" for entry in activity)
            ):
                _append_activity_bubble(parts, base, {"kind": "response", "text": message["content"]})
            for entry in activity:
                if entry["kind"] == "compaction":
                    _append_activity_bubble(
                        parts,
                        base,
                        {key: value for key, value in entry.items() if key not in {"summary", "keepMessages"}},
                        "notice",
                    )
                    if "summary" in entry:
                        parts.append(
                            {
                                **base,
                                "role": "user",
                                "source": "app",
                                "content": f"[Conversation summary]\n{entry['summary']}",
                                "presentation": "summary",
                                "compaction": entry,
                            }
                        )
                elif entry["kind"] == "notice" and entry["text"].startswith("Sent in future model context: "):
                    parts.append(
                        {
                            **base,
                            "role": "user",
                            "source": "app",
                            "title": "Context notice",
                            "content": entry["text"].removeprefix("Sent in future model context: "),
                            "presentation": "context",
                        }
                    )
                else:
                    _append_activity_bubble(
                        parts, base, entry, "notice" if entry["kind"] in {"notice", "schedule-applied"} else None
                    )
            if (
                message.get("status") == "pending"
                and parts[-1].get("presentation")
                and not any(
                    entry["kind"] == "compaction" and (entry["state"] == "running" or entry["reason"] == "manual")
                    for entry in activity
                )
            ):
                parts.append({**base, "content": ""})
            elif (
                message.get("status") in {"failed", "stopped"}
                and not any(part["role"] == "assistant" and not part.get("presentation") for part in parts)
                and not any(entry["kind"] == "compaction" and entry.get("reason") == "manual" for entry in activity)
            ):
                context_index = next(
                    (index for index, part in enumerate(parts) if part.get("presentation") == "context"),
                    len(parts),
                )
                parts.insert(context_index, {**base, "content": ""})
            footer = next(
                (
                    part
                    for part in reversed(parts)
                    if part["role"] == "assistant" and part.get("presentation") != "notice"
                ),
                next((part for part in reversed(parts) if part["role"] == "assistant"), parts[-1]),
            )
            footer.update({key: value for key, value in message.items() if key in footer_fields})
            for part in parts:
                if part is not footer and part.get("presentation") is None:
                    part["split"] = True
        part_counts = [_context_message_count(part) for part in parts]
        if (
            message["role"] == "assistant"
            and message.get("status") in {"failed", "stopped"}
            and not any(part_counts)
            and not any(entry["kind"] == "compaction" and entry.get("reason") == "manual" for entry in activity)
        ):
            for index in range(len(bubbles) - 1, -1, -1):
                if bubbles[index]["role"] == "assistant":
                    break
                if bubbles[index]["role"] == "user" and bubbles[index].get("source") == "status":
                    counts[index] = 0
                elif bubbles[index]["role"] == "user" and bubbles[index].get("source") in {None, "optimizer"}:
                    counts[index] = 0
                    break
        bubbles.extend(parts)
        counts.extend(part_counts)
    active = set()
    for index, bubble in enumerate(bubbles):
        if bubble.get("presentation") == "summary" and not bubble["compaction"].get("invalidated"):
            keep = bubble["compaction"].get("keepMessages", 0)
            retained = set()
            # Keep the newest messages. The new summary replaces the earlier one, so it never counts as kept.
            for prior in sorted(active, reverse=True):
                if keep <= 0:
                    break
                if counts[prior] > 0 and bubbles[prior].get("presentation") != "summary":
                    retained.add(prior)
                    keep -= counts[prior]
            retained.add(index)
            active = retained
        elif counts[index] > 0:
            active.add(index)
    for index, bubble in enumerate(bubbles):
        if counts[index] > 0 and index not in active:
            bubble["compacted"] = True
        yield bubble


def message_label(message):
    if message.get("presentation") == "notice":
        return "App notice"
    if message.get("presentation") == "summary":
        return (
            "Discarded conversation summary"
            if message["compaction"].get("invalidated")
            else "User · Conversation summary"
        )
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

    # `urls` maps upload event paths and filenames to bundled attachment paths when the
    # export carries files. Only upload event entries have a path.
    urls = urls or {}
    return [
        {
            "label": f"{file['filename']} ({size(file['bytes'])} KB)",
            "url": urls.get(file.get("path"), urls.get(file["filename"])),
        }
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


def _usd(value) -> str:
    amount = Decimal(value)
    if 0 < amount < Decimal("0.000001"):
        return "<$0.000001"
    text = f"{amount:,.6f}"
    while text.endswith("0") and len(text.partition(".")[2]) > 4:
        text = text[:-1]
    return "$" + text


def _cost_summary_text(message):
    summary, calls = message["costSummary"], message.get("providerCalls", [])
    running = message.get("status") == "pending"
    known_pending = sum(call["status"] == "pending" and call.get("cost_usd") is not None for call in calls)
    pending = summary["pending"] if running else 0
    unavailable = summary["unavailable"] + (0 if running else max(0, summary["pending"] - known_pending))
    price = _usd(summary["usd"])
    price = price if price.startswith("<") else "~" + price
    streaming = summary.get("streaming", {})
    speed = _streaming_speed(streaming.get("output_tokens"), streaming.get("seconds"))
    text = f"Turn details · {price} · {speed} · {summary['calls']} "
    text += "call" if summary["calls"] == 1 else "calls"
    if pending:
        text += f" · {pending} pending"
    if unavailable:
        text += f" · {unavailable} cost unavailable"
    return text


def _metric_number(value, places):
    rounded = Decimal(str(value)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    return f"{rounded:,f}".rstrip("0").rstrip(".")


def _streaming_speed(tokens, seconds):
    return _metric_number(tokens / seconds, 1) + " tok/s" if tokens and seconds else "Speed unavailable"


def _seconds(seconds):
    return _metric_number(seconds, 3) + "s"


def _turn_measurement_lines(summary):
    streaming = summary.get("streaming", {})
    count = summary["calls"]
    return [
        f"Estimated cost: {_usd(summary['usd'])}",
        "Provider streaming speed: " + _streaming_speed(streaming.get("output_tokens"), streaming.get("seconds")),
        f"Speed measured for {streaming.get('calls', 0)} of {count} {'call' if count == 1 else 'calls'}.",
        (
            "Measured from first to last output chunk. Includes reported reasoning and tool-call output tokens. "
            "Excludes time to first output, tool execution, VM work, and retry delays. "
            "Provider buffering can affect this estimate."
        ),
    ]


def _provider_cost_lines(call, index, running):
    price = (
        _usd(call["cost_usd"])
        if call.get("cost_usd") is not None
        else "Cost pending"
        if call["status"] == "pending" and running
        else "Cost unavailable"
    )
    lines = [f"{index}. {call['model']} · {call.get('reasoning', 'default')} · {price}"]
    if call.get("response_model") and call["response_model"] != call["model"]:
        lines.append("Reported model: " + call["response_model"])
    if usage := call.get("usage"):
        labels = [
            ("Input", "prompt_tokens"),
            ("Output", "completion_tokens"),
            ("Cached input", "cached_prompt_tokens"),
            ("Reasoning (included in output)", "reasoning_tokens"),
        ]
        lines.append(
            " · ".join(
                f"{label}: {usage[key]:,}"
                for label, key in labels
                if usage.get(key) is not None and (key != "reasoning_tokens" or usage[key])
            )
        )
    speed = "Provider streaming speed: " + _streaming_speed(
        (call.get("usage") or {}).get("completion_tokens"), call.get("streaming_seconds")
    )
    if call.get("streaming_seconds") is not None:
        speed += " · Streaming: " + _seconds(call["streaming_seconds"])
    if call.get("time_to_first_output_seconds") is not None:
        speed += " · Time to first output: " + _seconds(call["time_to_first_output_seconds"])
    lines.append(speed)
    lines.append("Call: " + (call.get("provider_call_id") or call["call_id"]))
    return lines


def _model_cost_lines(message) -> list[str]:
    """Always include saved model and cost details, independent of browser settings."""
    lines = []
    if selection := message.get("modelSelection"):
        lines.append(f"Model: {selection['model']} · {selection['reasoning']}")
    if message.get("costSummary"):
        lines.append(_cost_summary_text(message))
        lines.extend(_turn_measurement_lines(message["costSummary"]))
        for index, call in enumerate(message.get("providerCalls", []), 1):
            lines.extend(_provider_cost_lines(call, index, message.get("status") == "pending"))
    return lines


def _model_cost_html(message):
    result = ""
    if message.get("costSummary"):
        result = (
            '<details class="cost-details"><summary>'
            + escape_html(_cost_summary_text(message))
            + '</summary><div class="turn-metrics">'
            + "".join(
                "<div>" + escape_html(line) + "</div>" for line in _turn_measurement_lines(message["costSummary"])
            )
            + '</div><ul class="cost-calls" aria-label="Provider calls">'
        )
        for index, call in enumerate(message.get("providerCalls", []), 1):
            lines = _provider_cost_lines(call, index, message.get("status") == "pending")
            result += (
                '<li class="cost-call">'
                + "".join(
                    "<div"
                    + (' class="cost-call-id"' if i == len(lines) - 1 else "")
                    + ">"
                    + escape_html(line)
                    + "</div>"
                    for i, line in enumerate(lines)
                )
                + "</li>"
            )
        result += "</ul></details>"
    if selection := message.get("modelSelection"):
        reasoning = "Default reasoning" if selection["reasoning"] == "default" else selection["reasoning"]
        result += '<div class="model-selection">' + escape_html(selection["model"] + " · " + reasoning) + "</div>"
    return result


def _compaction_summary_html(entry):
    paragraphs, text = _compaction_summary_text(entry).split("\n\n[Conversation summary]\n", 1)
    return "".join(
        '<p class="summary-explanation">' + escape_html(line) + "</p>" for line in paragraphs.split("\n")
    ) + _chunked_text("[Conversation summary]\n" + text, "summary")


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
    for message in _display_messages(messages):
        lines += ["", "## " + message_label(message)]
        if message.get("presentation") == "notice":
            lines += ["", "Not sent to AI."]
        elif message.get("compacted"):
            lines += ["", "Compacted out of context."]
        files = _message_files(message, urls)
        if files:
            lines += ["", *["- " + _file_markdown(file) for file in files]]
        if message.get("presentation") == "summary":
            lines += ["", "```text", _compaction_summary_text(message["compaction"]), "```"]
        elif message["role"] == "optimizer":
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
                    lines += ["", _activity_text(entry) or "[No message text]"]
                    lines += ["", _count(entry["text"]) + " characters"]
                else:
                    lines += ["", "### " + _activity_label(entry), "", "```text", _activity_text(entry), "```"]
        details = _model_cost_lines(message)
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
    for message in _display_messages(messages):
        role = message["role"]
        presentation = message.get("presentation")
        compaction = message.get("compaction") if presentation == "summary" else None
        notice = presentation == "notice" or (compaction and compaction.get("invalidated"))
        source = " " + message["source"] if message.get("source") else ""
        if notice:
            source += " app-notice"
        files = _message_files(message, urls)
        uploads = (
            '<ul class="attachments" aria-label="Uploaded files in this message">'
            + "".join("<li>" + _file_html(file) + "</li>" for file in files)
            + "</ul>"
            if files
            else ""
        )
        if compaction:
            timeline = (
                '<details class="system-prompt"><summary class="collapsed-summary">Conversation summary</summary>'
                + _compaction_summary_html(compaction)
                + "</details>"
            )
        elif presentation == "context":
            timeline = '<p class="context-content">' + escape_html(message["content"]) + "</p>"
        elif role == "assistant":
            entries, fragments = _timeline(message, html=True), []
            for index, entry in enumerate(entries):
                separator = (
                    '<hr class="activity-separator">'
                    if index > 0 and (entry["kind"] == "response" or entries[index - 1]["kind"] == "response")
                    else ""
                )
                content = (
                    '<div class="content">'
                    + render_markdown_html(entry["text"])
                    + '</div><p class="character-count">'
                    + _count(entry["text"])
                    + " characters</p>"
                    if entry["kind"] == "response"
                    else _activity_html(entry)
                )
                # Match the live chat: model inputs align right and app notices center.
                placement = (
                    " model-input"
                    if entry["kind"] == "schedule-check"
                    else " app-notice"
                    if entry["kind"] in {"schedule-applied", "notice"}
                    else ""
                )
                if entry["kind"] in {"response", "reasoning"} and entry.get("context") == "omitted":
                    content = (
                        '<p class="omitted-response">Incomplete response. Omitted from future model context.</p>'
                        + content
                    )
                if entry["kind"] == "schedule-applied" and entry.get("notice"):
                    content = (
                        '<p role="status" class="schedule-notice">' + escape_html(entry["notice"]) + "</p>" + content
                    )
                fragments.append(f'<div class="activity-entry{placement}">' + separator + content + "</div>")
            timeline = (
                '<div class="assistant-activity" aria-label="Assistant activity">' + "".join(fragments) + "</div>"
            )
        elif role == "system" or message.get("source"):
            timeline = f'<details class="system-prompt"><summary class="collapsed-summary">{_count(message["content"])} characters</summary><pre class="collapsed-output">{escape_html(message["content"])}</pre></details>'
        elif role == "optimizer":
            summary, details = _optimizer_parts(message["content"])
            rows = "".join(
                f'<div class="optimizer-detail"><dt class="optimizer-label">{escape_html(label)}:</dt> <dd class="optimizer-value">{escape_html(value)}</dd></div>'
                for label, value in details
            )
            timeline = (
                '<p class="plain-content">'
                + escape_html(summary or "[No message text]")
                + "</p>"
                + ('<dl class="optimizer-details">' + rows + "</dl>" if rows else "")
            )
        else:
            timeline = '<p class="plain-content">' + escape_html(message["content"] or "[No message text]") + "</p>"
        status, timing = "", ""
        if message.get("status") == "pending" and not message["content"] and not notice:
            timeline += (
                '<span role="status" aria-label="Thinking" class="thinking"><span>Thinking</span>'
                '<span aria-hidden="true" class="thinking-dots">'
                + "".join(
                    f'<span class="thinking-dot" style="animation-delay:{index * 160}ms"></span>' for index in range(3)
                )
                + "</span></span>"
            )
        elif message.get("status") == "failed":
            reason = message.get("failureReason")
            shown = any(
                entry["kind"] == "response" and entry["text"] == reason for entry in _timeline(message, html=True)
            )
            if reason and not shown:
                status = '<p class="failure-reason">' + escape_html(reason) + "</p>"
            status += '<p class="failure">This response failed before completion. Send a new message to continue.</p>'
        elif message.get("status") == "stopped":
            status = '<p class="stopped">Stopped before completion.</p>'
        at = message.get("responseCompletedAt", message.get("createdAt"))
        if at is not None:
            iso = _iso(at)
            display = iso.replace("T", " ").replace("Z", " UTC")
            duration = (
                " · " + _duration(message["responseStartedAt"], message["responseCompletedAt"])
                if "responseStartedAt" in message and "responseCompletedAt" in message
                else ""
            )
            timing = f'<time class="message-time" datetime="{iso}" title="{escape_html(display)}">{escape_html(display)}{duration}</time>'
        # Messages reach the model by default, so only exceptions get a status line.
        audience = (
            '<p class="message-status">Omitted from future model context.</p>'
            if compaction and compaction.get("invalidated")
            else '<p class="message-status">Compacted out of context.</p>'
            if message.get("compacted")
            else '<p class="message-status">Not sent to AI.</p>'
            if presentation == "notice" or role == "optimizer"
            else ""
        )
        model_cost = _model_cost_html(message)
        if message.get("truncated"):
            warning = '<p class="truncated">A response reached the output token limit. Tool calls in that response were not executed.</p>'
            status = warning + status if message.get("status") == "failed" else status + warning
        rendered.append(f"""
      <article class="message {role}{source}">
        <div class="label">{escape_html(message_label(message))}</div>
        {audience}
        {uploads}
        {timeline}
        {model_cost}{timing}{status}
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
        styles=Path(__file__).with_name("chat_styles.css").read_text(encoding="utf-8"),
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
