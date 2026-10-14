"""Extract local Schedule AI Chat HTML exports without executing their contents."""

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
# This file is mostly AI generated.

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
BLOCK_TAGS = {"div", "p", "li", "pre", "h1", "h2", "h3", "h4", "dt", "dd", "tr"}


@dataclass
class Node:
    tag: str = ""
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)

    def find(self, css_class):
        for child in self.children:
            if isinstance(child, Node):
                if css_class in (child.attrs.get("class") or "").split():
                    yield child
                else:
                    yield from child.find(css_class)

    def text(self):
        if self.tag in {"script", "style"}:
            return ""
        if self.tag == "br":
            return "\n"
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                value = child.text()
                parts.append(value)
                if child.tag in BLOCK_TAGS and value and not value.endswith("\n"):
                    parts.append("\n")
        return "".join(parts)


class ExportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def texts(node, css_class, *, strip=True):
    values = [part.text() for part in node.find(css_class)]
    return [value.strip() for value in values] if strip else values


def extract_export(html, *, include_reasoning=False):
    parser = ExportParser()
    parser.feed(html)
    parser.close()
    messages = []
    counts = Counter()
    failed_tools = interrupted_tools = reasoning_entries = 0
    for node in parser.root.find("message"):
        if node.tag != "article":
            continue
        classes = (node.attrs.get("class") or "").split()
        # The first class after "message" is the provider role. Later classes
        # identify app/status/optimizer sources of user-role messages.
        role_index = classes.index("message") + 1
        role = classes[role_index] if role_index < len(classes) else "unknown"
        activity = []
        for index, entry in enumerate(node.find("activity-entry")):
            details = next(entry.find("activity-details"), None)
            if details is None:
                activity.append(
                    {
                        "index": index,
                        "kind": "response",
                        "content": texts(entry, "content"),
                    }
                )
                continue
            summary = next(
                (
                    c.text().strip()
                    for c in details.children
                    if isinstance(c, Node) and c.tag == "summary"
                ),
                "",
            )
            outputs = texts(details, "activity-output", strip=False)
            if summary.startswith("Reasoning"):
                reasoning_entries += 1
                if include_reasoning:
                    activity.append(
                        {"index": index, "kind": "reasoning", "outputs": outputs}
                    )
            elif list(details.find("schedule-diff")):
                activity.append(
                    {
                        "index": index,
                        "kind": "schedule-change",
                        "diff": texts(details, "schedule-diff", strip=False),
                    }
                )
            elif list(details.find("tool-body")):
                name, separator, state = summary.partition(" · ")
                state = state if separator else "completed"
                counts[name] += 1
                failed_tools += state == "failed"
                interrupted_tools += state == "interrupted"
                activity.append(
                    {
                        "index": index,
                        "kind": "tool",
                        "name": name,
                        "state": state,
                        "outputs": outputs,
                    }
                )
        timing = [
            {
                "datetime": c.attrs.get("datetime"),
                "title": c.attrs.get("title"),
                "display": c.text().strip(),
            }
            for c in node.children
            if isinstance(c, Node) and c.tag == "time"
        ]
        collapsed_text = [
            child.text()
            for prompt in node.find("system-prompt")
            for child in prompt.children
            if isinstance(child, Node) and child.tag == "pre"
        ]
        messages.append(
            {
                "index": len(messages),
                "role": role,
                "sources": classes[role_index + 1 :],
                "label": texts(node, "label"),
                "content": texts(node, "content") + ([] if role == "system" else collapsed_text),
                "system_prompts": collapsed_text if role == "system" else [],
                "activity": activity,
                "failures": texts(node, "failure"),
                "status": texts(node, "message-status"),
                "optimizer_details": texts(node, "optimizer-details"),
                "timing": timing,
            }
        )
    if not messages:
        raise ValueError("No Schedule AI Chat message articles found")
    inventory = {
        "messages": len(messages),
        "tool_calls": sum(counts.values()),
        "tools": dict(sorted(counts.items())),
        "failed_tool_calls": failed_tools,
        "interrupted_tool_calls": interrupted_tools,
        "failed_assistant_turns": sum(
            m["role"] == "assistant" and bool(m["failures"]) for m in messages
        ),
        "reasoning_entries": reasoning_entries,
    }
    return {
        "metadata": texts(parser.root, "metadata"),
        "sections": [
            {"label": n.attrs.get("aria-label"), "text": n.text().strip()}
            for n in parser.root.find("proposal")
        ],
        "messages": messages,
        "inventory": inventory,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", type=Path, nargs="+", help="HTML exports. Expand globs in the shell."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/trace-investigation/extracted"),
    )
    parser.add_argument(
        "--include-reasoning",
        action="store_true",
        help="Include reasoning only when needed for investigation.",
    )
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inventories = []
    for index, source in enumerate(sorted(set(args.inputs)), 1):
        try:
            report = extract_export(
                source.read_text(encoding="utf-8"),
                include_reasoning=args.include_reasoning,
            )
        except (OSError, ValueError) as error:
            parser.exit(1, f"{source}: {error}\n")
        report["source"] = str(source)
        destination = args.output_dir / f"trace-{index:03d}.json"
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        inventory = {
            "source": str(source),
            "report": str(destination),
            **report["inventory"],
        }
        inventories.append(inventory)
        print(json.dumps(inventory, ensure_ascii=False))
    (args.output_dir / "inventory.json").write_text(
        json.dumps(inventories, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
