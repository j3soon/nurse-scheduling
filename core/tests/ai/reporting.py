"""Save testcase transcripts and print failures and attempt summaries."""

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

import json
from pathlib import Path

from nurse_scheduling.ai.config import AiSettings

from .schema import Case


def _block(text: str, language: str = "") -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{language}\n{text}\n{fence}\n"


def _transcript(record: dict) -> str:
    lines = [f"# {Path(record['case']).name}: {'PASS' if record['passed'] else 'FAIL'}\n"]
    lines.append(f"Model: `{record['model']}`. Sandbox template: `{record['template']}`.\n")
    if record["error"]:
        lines.extend(["## Failures\n", _block(record["error"])])
    for turn in record["turns"]:
        lines.extend([f"## Turn {turn['turn']}\n", "### User\n", _block(turn["user"])])
        if turn["attachments"]:
            lines.extend(["### Attachments\n", _block(json.dumps(turn["attachments"], indent=2), "json")])
        for event in turn["events"]:
            lines.append(f"### {event['kind'].replace('_', ' ').title()}\n")
            if event["kind"] == "assistant":
                lines.append(_block(event["text"]))
                if event.get("reasoning"):
                    lines.extend(["Reasoning:\n", _block(event["reasoning"])])
                lines.append(
                    _block(
                        json.dumps(
                            {key: value for key, value in event.items() if key not in {"kind", "text", "reasoning"}},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "json",
                    )
                )
            elif event["kind"] == "judge":
                if "attempt" in event:
                    lines.append(f"Judge attempt: {event['attempt']}.\n")
                lines.append(f"Verdict: **{'PASS' if event['passed'] else 'FAIL'}**. Model: `{event['model']}`.\n")
                lines.extend(["Rubric:\n", _block(event["rubric"]), "Explanation:\n", _block(event["reason"])])
                if event["error"]:
                    lines.append(_block(event["error"]))
                lines.extend(["Raw response:\n", _block(event["response"], "json")])
                lines.extend(
                    ["Judge request:\n", _block(json.dumps(event["messages"], ensure_ascii=False, indent=2), "json")]
                )
                if event["reasoning"]:
                    lines.extend(["Judge reasoning:\n", _block(event["reasoning"])])
            elif event["kind"] == "tool_result":
                lines.append(f"Tool: `{event['name']}`, succeeded: `{event['ok']}`.\n")
                lines.append(_block(event["text"]))
            else:
                lines.append(_block(json.dumps(event, ensure_ascii=False, indent=2), "json"))
        lines.extend(
            [
                "### Schedule before\n",
                _block(turn["before"], "yaml"),
                "### Schedule after\n",
                _block(turn["after"], "yaml"),
            ]
        )
    return "\n".join(lines)


def print_attempt(
    case: Case,
    errors: list[dict],
    trace: list[dict],
    settings: AiSettings,
    transcript_path: Path | None = None,
) -> None:
    record = {
        "case": str(case.path),
        "model": settings.provider_model,
        "template": settings.e2b_template,
        "passed": not errors,
        "error": "\n".join(
            f"turn {item['turn']}, step {item['step']} ({item['kind']}): {item['error']}" for item in errors
        ),
        "turns": trace,
    }
    text = _transcript(record)
    for secret in (settings.provider_api_key, settings.e2b_api_key):
        if secret:
            text = text.replace(secret, "[redacted]")
    if transcript_path is not None:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(text, encoding="utf-8")
    location = f"; transcript: {transcript_path}" if transcript_path is not None else ""
    if errors:
        print(text + (f"\nTranscript: {transcript_path}" if transcript_path is not None else ""), flush=True)
    else:
        print(f"PASS {case.path} ({len(trace)} turns){location}", flush=True)


def print_summary(results: list[dict]) -> None:
    text = (
        "# AI testcase attempts\n\nAny failed attempt keeps CI failed. Later attempts provide diagnostic evidence.\n\n"
    )
    text += "| Case | Attempt | Outcome |\n| --- | --- | --- |\n"
    for item in results:
        text += f"| {item['case']} | {item['attempt']} | {'PASS' if item['passed'] else 'FAIL'} |\n"
    text += "\n| Case | Failed / executed attempts |\n| --- | --- |\n"
    for case in dict.fromkeys(item["case"] for item in results):
        attempts = [item for item in results if item["case"] == case]
        text += f"| {case} | {sum(not item['passed'] for item in attempts)}/{len(attempts)} |\n"
    print(text, flush=True)
