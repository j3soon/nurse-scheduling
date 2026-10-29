"""Project saved session events into the historical chat export format."""

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

from typing import Any

from .costs import CostTotals
from .provider import ProviderCall


def _finish(message: dict, kind: str, at: int, reason: str = "") -> None:
    message["status"] = {"done": None, "stopped": "stopped"}.get(kind, "failed")
    message["responseCompletedAt"] = at
    message.pop("failureReason", None)
    if kind == "stale":
        message["content"] = reason
        message["activity"] = [{"kind": "response", "text": reason}]
    elif kind == "error":
        message["content"] = message["content"] or reason
        if reason:
            message["failureReason"] = reason
    if kind != "done":
        for entry in message.get("activity", []):
            if entry["kind"] in {"tool", "compaction"} and entry.get("state") in {"running", "preparing"}:
                entry["state"] = "interrupted"


def _invalidate_summaries(turn: dict) -> None:
    for message in turn["assistants"]:
        for entry in message.get("activity", []):
            if entry["kind"] == "compaction" and entry.get("state") == "completed":
                entry["invalidated"] = True


def _optimization_text(data: dict) -> str:
    state = data["state"]
    text = (
        (
            "Optimization finished. Download the optimized schedule to review it."
            if data.get("downloadable")
            else "Optimization finished, but no result workbook is available to download."
        )
        if state == "completed"
        else f"Optimization ended with status: {state}."
    )
    lines = [text]

    def add(label, value):
        if value is not None:
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            lines.append(f"{label}: " + str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\n "))

    result, request, backend, error = (data.get(key) or {} for key in ("result", "request", "backend", "error"))
    if data.get("elapsed_seconds") is not None:
        total = max(0, int(data["elapsed_seconds"]))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        add("Elapsed time", f"{f'{hours}h ' if hours else ''}{f'{minutes}m ' if hours or minutes else ''}{seconds}s")
    add("Finish now requested by", data.get("finish_now_requested_by"))
    for label, value in (
        ("Outcome", result.get("outcome")),
        ("Final score", result.get("score")),
        ("Solver", request.get("solver")),
        ("Solver status", result.get("solver_status")),
        ("Termination reason", result.get("termination_reason")),
    ):
        add(label, value)
    if request.get("timeout_seconds") is not None:
        add("Solver timeout", f"{request['timeout_seconds']}s")
    if data.get("backend") is not None:
        for label, key in (
            ("Backend URL", "url"),
            ("Backend version", "app_version"),
            ("API version", "api_version"),
            ("Service", "service_name"),
            ("Deployment", "deployment_id"),
            ("Instance", "instance_id"),
        ):
            add(label, backend.get(key, "unknown" if key in {"url", "app_version"} else None))
        if backend.get("request_timeout_seconds") is not None:
            add("Backend request timeout", f"{backend['request_timeout_seconds']}s")
        claimed = backend.get("claimed_performance") or {}
        add(
            "Claimed performance",
            f"{claimed['score']} (version {claimed['app_version']}, measured {claimed['measured_at']})"
            if claimed.get("score", 0) > 0 and claimed.get("app_version") and claimed.get("measured_at")
            else "unavailable",
        )
    add("Error code", error.get("code"))
    add("Error", error.get("message"))
    return "\n".join(lines)


def project_saved_chat(snapshot: dict[str, Any]) -> tuple[list[dict], dict]:
    """Reproduce the browser transcript using stored UTC event timestamps."""
    if snapshot.get("schema_version") != 1:
        raise ValueError("Unsupported saved chat snapshot")
    messages, turns = [], {}
    runs = {run["id"]: run for run in snapshot["runs"]}
    optimization = None
    supported = {
        "run_start",
        "model_input",
        "model_selection",
        "provider_call",
        "cost_summary",
        "steering",
        "delta",
        "reasoning",
        "tool_start",
        "tool",
        "download",
        "schedule_change",
        "schedule_applied",
        "truncated",
        "provider_retry",
        "response_end",
        "compaction_start",
        "compaction_end",
        "generation_progress",
        "done",
        "stopped",
        "error",
        "stale",
    }
    for raw in snapshot["events"]:
        kind, data, at = raw["type"], raw["data"], raw["occurred_at"]
        if kind == "optimization":
            if data.get("terminal"):
                if optimization and optimization["job_id"] == data["job_id"]:
                    optimization = None
                identity = "optimizer-" + data["job_id"]
                if not any(message.get("id") == identity for message in messages):
                    messages.append(
                        {"id": identity, "role": "optimizer", "content": _optimization_text(data), "createdAt": at}
                    )
            else:
                optimization = data
            continue
        if kind == "optimization_progress":
            if optimization is None:
                optimization = {**data, "state": "running"}
            continue
        run_id = data.get("run_id")
        if not run_id or kind not in supported:
            continue
        if run_id not in turns:
            run = runs.get(run_id, {})
            question = None
            if run.get("kind") == "foreground":
                question = {"role": "user", "content": run.get("prompt", ""), "createdAt": run.get("started_at", at)}
                messages.append(question)
            assistant = {
                "role": "assistant",
                "content": "",
                "status": "pending",
                "responseStartedAt": run.get("started_at", at),
            }
            messages.append(assistant)
            turns[run_id] = {
                "question": question,
                "assistant": assistant,
                "assistants": [assistant],
                "cost_assistant": assistant,
                "calls": {},
                "has_output": False,
                "schedule": "",
                "working": None,
            }
        turn = turns[run_id]
        assistant = turn["assistant"]
        activity = assistant.setdefault("activity", [])
        if kind == "generation_progress":
            if data["kind"] == "compaction":
                entry = next(
                    (
                        item
                        for item in reversed(activity)
                        if item["kind"] == "compaction" and item["state"] == "running"
                    ),
                    None,
                )
                if entry is not None:
                    entry.update(characters=data["characters"], step=data["step"])
            else:
                entry = {
                    "kind": "tool",
                    "name": "Tool calls",
                    "arguments": "",
                    "result": "",
                    "ok": True,
                    "state": "preparing",
                    "argumentsCharacters": data["characters"],
                }
                index = next(
                    (
                        i
                        for i, item in enumerate(activity)
                        if item["kind"] == "tool" and item.get("state") == "preparing"
                    ),
                    None,
                )
                if index is None:
                    activity.append(entry)
                else:
                    activity[index] = entry
                turn["has_output"] = True
        elif kind in {"compaction_start", "compaction_end"}:
            if data["reason"] == "manual" and not any(
                entry["kind"] == "compaction" and entry["reason"] == "manual" for entry in activity
            ):
                activity.append({"kind": "notice", "text": "You requested context compaction."})
            state = (
                "running"
                if kind == "compaction_start"
                else "completed"
                if data["success"]
                else "interrupted"
                if data.get("aborted")
                else "skipped"
                if data.get("skipped")
                else "failed"
            )
            entry = {
                "kind": "compaction",
                "state": state,
                "reason": data["reason"],
                "text": "The conversation is being summarized."
                if state == "running"
                else "The conversation was summarized."
                if state == "completed"
                else "Summarization stopped. The original context was kept."
                if state == "interrupted"
                else "Nothing to compact. The original context was kept."
                if state == "skipped"
                else "Summarization failed. The original context was kept.",
            }
            if "summary" in data:
                entry.update(summary=data["summary"], keepMessages=data.get("keep_messages", 0))
            index = next(
                (
                    index
                    for index in range(len(activity) - 1, -1, -1)
                    if activity[index]["kind"] == "compaction" and activity[index].get("state") == "running"
                ),
                None,
            )
            if kind == "compaction_end" and index is not None:
                for key in ("characters", "step"):
                    if key in data or key in activity[index]:
                        entry[key] = data.get(key, activity[index].get(key))
                activity[index] = entry
            else:
                for key in ("characters", "step"):
                    if key in data:
                        entry[key] = data[key]
                activity.append(entry)
        elif kind == "model_selection":
            selection = {key: data[key] for key in ("model", "reasoning")}
            turn["selection"] = selection
            assistant["modelSelection"] = selection
        elif kind == "provider_call":
            turn["calls"][data["call_id"]] = data
        elif kind == "cost_summary":
            turn["cost_assistant"]["costSummary"] = data["run"]
        elif kind == "model_input":
            turn["schedule"] = data.get("schedule_yaml", turn["schedule"])
            previous_system = next((m for m in reversed(messages) if m["role"] == "system"), None)
            before = (
                []
                if previous_system and previous_system["content"] == data["system"]
                else [{"role": "system", "content": data["system"]}]
            )
            known = {m.get("historyIndex") for m in messages}
            status, question_text, optimizer_text = None, None, None
            for entry in data["messages"]:
                if entry["kind"] == "app" and entry["index"] not in known:
                    before.append(
                        {
                            "role": "user",
                            "source": "app",
                            "historyIndex": entry["index"],
                            "title": entry.get("title"),
                            "content": entry["content"],
                        }
                    )
                elif entry["kind"] == "status":
                    status = {
                        "role": "user",
                        "source": "status",
                        "title": entry.get("title"),
                        "content": entry["content"],
                        **({"historyIndex": entry["index"]} if "index" in entry else {}),
                    }
                elif entry["kind"] == "question":
                    question_text = entry["content"]
                elif entry["kind"] == "optimizer":
                    optimizer_text = entry["content"]
            question = turn["question"] if question_text is not None else None
            if question is not None:
                question["content"] = question_text
            if optimizer_text is not None:
                question = turn.get("optimizer")
                if question is None:
                    question = {"role": "user", "source": "optimizer", "content": optimizer_text}
                    messages.insert(next(i for i, m in enumerate(messages) if m is assistant), question)
                    turn["optimizer"] = question
                else:
                    question["content"] = optimizer_text
            target = question if question is not None else assistant
            index = next(i for i, m in enumerate(messages) if m is target)
            messages[index:index] = before
            if status is not None:
                messages.insert(next(i for i, m in enumerate(messages) if m is assistant), status)
        elif kind == "steering":
            index = next(i for i, m in enumerate(messages) if m is assistant)
            question = {"role": "user", "content": data["message"], "createdAt": at}
            if turn["has_output"]:
                _finish(assistant, "done", at)
                assistant = {"role": "assistant", "content": "", "status": "pending", "responseStartedAt": at}
                if "selection" in turn:
                    assistant["modelSelection"] = turn["selection"]
                messages[index + 1 : index + 1] = [question, assistant]
                turn["assistants"].append(assistant)
                turn["assistant"], turn["has_output"] = assistant, False
            else:
                messages.insert(index, question)
        elif kind in {"delta", "reasoning"}:
            text = data["text"]
            entry_kind = "response" if kind == "delta" else "reasoning"
            if kind == "delta":
                assistant["content"] += text
            if activity and activity[-1]["kind"] == entry_kind and "context" not in activity[-1]:
                activity[-1]["text"] += text
            else:
                activity.append({"kind": entry_kind, "text": text})
            turn["has_output"] |= bool(text)
        elif kind == "response_end":
            # A new model response follows the latest tool result, which ends its tool round.
            if tools := [entry for entry in activity if entry["kind"] == "tool" and entry.get("state") != "preparing"]:
                tools[-1]["endsRound"] = True
            for entry in activity:
                if entry["kind"] in {"response", "reasoning"} and "context" not in entry:
                    omitted = data["stop_reason"] in {"error", "aborted"} or data.get("context_omitted")
                    entry["context"] = "omitted" if omitted else "complete"
            if data.get("context_note"):
                _invalidate_summaries(turn)
                activity.append({"kind": "notice", "text": f"Sent in future model context: {data['context_note']}"})
            if data["stop_reason"] == "length":
                assistant["truncated"] = True
        elif kind == "truncated":
            assistant["truncated"] = True
        elif kind in {"tool_start", "tool"}:
            entry = {
                "kind": "tool",
                "name": data["name"],
                "arguments": data.get("arguments", ""),
                "result": data.get("result", ""),
                "ok": data.get("ok") is not False,
            }
            if "replay_arguments" in data:
                entry["replayArguments"] = data["replay_arguments"]
            if "tool_call_id" in data:
                entry["toolCallId"] = data["tool_call_id"]
            if kind == "tool_start":
                activity[:] = [item for item in activity if item["kind"] != "tool" or item.get("state") != "preparing"]
                entry["state"] = "running"
                activity.append(entry)
            else:
                completed = [entry]
                if check := data.get("schedule_check"):
                    completed.append({"kind": "schedule-check", **check})
                index = next(
                    (
                        i
                        for i, item in enumerate(activity)
                        if item["kind"] == "tool"
                        and item.get("state") == "running"
                        and (
                            item.get("toolCallId") == entry["toolCallId"]
                            if "toolCallId" in entry
                            else item["name"] == entry["name"]
                        )
                    ),
                    None,
                )
                if index is None:
                    activity.extend(completed)
                else:
                    activity[index : index + 1] = completed
            turn["has_output"] = True
        elif kind == "schedule_change":
            activity.append(
                {
                    "kind": "schedule-change",
                    "before": turn["working"] if turn["working"] is not None else turn["schedule"],
                    "after": data["schedule_yaml"],
                }
            )
            turn["working"] = data["schedule_yaml"]
            turn["has_output"] = True
        elif kind == "provider_retry":
            activity[:] = [item for item in activity if item["kind"] != "tool" or item.get("state") != "preparing"]
            activity.append({"kind": "notice", "text": data["message"]})
        elif kind == "schedule_applied":
            activity[:] = [a for a in activity if a["kind"] != "schedule-applied" or a.get("runId") != run_id]
            entry = {"kind": "schedule-applied", "text": data["diff"], "runId": run_id}
            if data.get("replaced_queued_schedule"):
                entry["notice"] = (
                    "The assistant’s schedule replaced changes made during this response. Undo to restore your previous schedule."
                )
            activity.append(entry)
        elif kind in {"done", "stopped", "error", "stale"}:
            if kind != "done":
                _invalidate_summaries(turn)
            _finish(
                assistant,
                kind,
                at,
                data.get("message", "The AI response became stale." if kind == "stale" else "The AI request failed."),
            )
    for run_id, turn in turns.items():
        if turn["calls"]:
            totals = CostTotals()
            for call in turn["calls"].values():
                totals.update(ProviderCall.restored(call))
            turn["cost_assistant"]["costSummary"] = totals.public()
            turn["cost_assistant"]["providerCalls"] = list(turn["calls"].values())
        run = runs.get(run_id, {})
        if turn["assistant"].get("status") == "pending" and run.get("status", "running") != "running":
            kind = {"cancelled": "stopped", "completed": "done"}.get(run["status"], "error")
            if kind != "done":
                _invalidate_summaries(turn)
            _finish(
                turn["assistant"],
                kind,
                run.get("finished_at") or snapshot["snapshot_at"],
                "This response did not complete.",
            )
    source = snapshot["metadata"]
    metadata = {
        "endpoint": source.get("endpoint", "unknown"),
        "exportedAt": snapshot["snapshot_at"],
        "frontendVersion": snapshot["frontend_version"],
        "backendVersion": source.get("backend_version", "unknown"),
        "uploadedFiles": source.get("uploaded_files", []),
        "fileUrls": source.get("file_urls", {}),
    }
    if optimization:
        request = optimization.get("request") or {}
        metadata["runningOptimization"] = {
            "jobId": optimization["job_id"],
            "state": optimization["state"],
            "solver": request.get("solver"),
            "timeoutSeconds": request.get("timeout_seconds"),
        }
    return messages, metadata
