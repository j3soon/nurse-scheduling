"""Test report extension, measured-input checks and preserved attempts."""

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

import asyncio
import json
from pathlib import Path

import pytest

from nurse_scheduling.ai.provider import TokenUsage
from nurse_scheduling.ai.sandbox.fake import FakeSandboxFactory
from nurse_scheduling.ai.workspace import WorkspaceMetrics

from .ai_eval import runner
from .ai_eval.report_extension import read_completed_reports
from .test_ai_eval_runner import CASE_BY_ID, ConcurrentProvider, _factory, settings


def saved_report(root, *, paired=False, repetitions=3, failed=False, cost_target=None):
    cases = [CASE_BY_ID[case_id] for case_id in ["ask-people-count", "ask-group-size"]]
    variants = (
        (("before", runner.prompt_at_step(0)), ("after", runner.prompt_at_step(1)))
        if paired
        else (("production", runner.SANDBOX_SYSTEM_PROMPT),)
    )
    metadata = {
        label: runner._evaluation_metadata(settings(), cases, repetitions, prompt) for label, prompt in variants
    }
    checkpoints = runner.RunCheckpoints(root, metadata, repetitions, len(cases) * repetitions * len(variants))
    runs = []
    for case in cases:
        for repetition in range(1, repetitions + 1):
            for label, _ in variants:
                run = runner.CaseRun(
                    case.id,
                    case.category,
                    not (failed and repetition == 1),
                    1.25,
                    2,
                    ["read"],
                    repetition=repetition,
                    prompt_variant=label,
                    token_usage=TokenUsage(100, 30, 130, None, 20),
                    token_usage_turns=1 if failed else 2,
                    provider_attempts=3,
                    provider_attempts_per_turn=[2, 1],
                    tool_calls_per_turn=[1, 0],
                    sandbox_metrics=WorkspaceMetrics(lifetime_seconds=1.125, execution_seconds=0.2),
                    trajectory={"question": case.question, "events": [{"kind": "text", "text": "Original evidence"}]},
                    error="provider unavailable" if failed and repetition == 1 else "",
                )
                runs.append(run)
                checkpoints.record(run)
    for label, _ in variants:
        runner.write_report(
            [r for r in runs if r.prompt_variant == label],
            checkpoints.directories[label],
            metadata=metadata[label],
            checkpointed=True,
        )
    if paired:
        metric, ratio = cost_target or (None, None)
        (root / "comparison.json").write_text(json.dumps({"cost_metric": metric, "cost_ratio": ratio}))
    checkpoints.set_status("complete")
    return cases, runs


def install_fake_runner(monkeypatch, calls):
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    monkeypatch.setattr(runner, "create_sandbox_factory", lambda _: FakeSandboxFactory())

    async def run_case(_provider, _settings, case, *args, **kwargs):
        calls.append((case.id, kwargs["system_prompt"]))
        return runner.CaseRun(
            case.id,
            case.category,
            True,
            1,
            1,
            [],
            token_usage=TokenUsage(100, 20, 120, 0, 10),
            token_usage_turns=1,
            trajectory={"events": [{"kind": "text", "text": "New evidence"}]},
        )

    monkeypatch.setattr(runner, "run_case", run_case)


def test_extension_keeps_original_attempts_and_runs_only_missing_selected_pairs(tmp_path, monkeypatch):
    source = tmp_path / "source"
    cases, _ = saved_report(source, paired=True)
    original = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    calls = []
    install_fake_runner(monkeypatch, calls)
    output = tmp_path / "extended"
    assert (
        runner.main(
            [
                "--extend-report",
                str(source),
                "--prompt-compare-step",
                "1",
                "--case",
                cases[0].id,
                "--repeat",
                "5",
                "--output-dir",
                str(output),
            ]
        )
        == 1
    )  # Correctness ties, no cost target.
    assert len(calls) == 4
    assert {case_id for case_id, _ in calls} == {cases[0].id}
    for label in ["before", "after"]:
        records = runner._load_report_records(output / label)
        assert [(r["case_id"], r["repetition"]) for r in records] == [(cases[0].id, n) for n in range(1, 6)] + [
            (cases[1].id, n) for n in range(1, 4)
        ]
        for n in range(1, 4):
            name = f"{cases[0].id}--run-{n}.json"
            assert json.loads((source / label / "cases" / name).read_text()) == json.loads(
                (output / label / "cases" / name).read_text()
            )
        metadata = json.loads((output / label / "metadata.json").read_text())
        assert metadata["repetitions_by_case"] == {cases[0].id: 5, cases[1].id: 3}
        assert metadata["extensions"][0]["first_repetitions"] == {cases[0].id: 4}
    assert json.loads((output / "progress.json").read_text()) == {"status": "complete", "completed": 16, "expected": 16}
    assert original == {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    statistics = json.loads((output / "comparison.json").read_text())
    assert statistics["cases"][cases[0].id]["metrics"]["total_tokens"]["pairs"] == 5
    assert statistics["cases"][cases[1].id]["metrics"]["total_tokens"]["pairs"] == 3


def test_extension_preserves_utf8_reports_with_a_legacy_windows_default(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _cases, runs = saved_report(source, paired=True)
    for run in runs:
        run.answer = "姓名"
        run.trajectory["events"] = [{"kind": "text", "text": "原始紀錄"}]
    for label in ("before", "after"):
        directory = source / label
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        metadata["note"] = "評估紀錄"
        runner.write_report(
            [run for run in runs if run.prompt_variant == label], directory, metadata=metadata, checkpointed=True
        )
    (source / "comparison.json").write_text(
        json.dumps({"cost_metric": None, "cost_ratio": None, "note": "比較紀錄"}, ensure_ascii=False), encoding="utf-8"
    )
    calls = []
    install_fake_runner(monkeypatch, calls)
    original_read_text = Path.read_text

    def legacy_read_text(path, encoding=None, errors=None, **kwargs):
        return original_read_text(path, encoding="cp1252" if encoding is None else encoding, errors=errors, **kwargs)

    monkeypatch.setattr(Path, "read_text", legacy_read_text)
    output = tmp_path / "extended"
    # A correctness tie returns 1. Both arms still contain four passing attempts per case.
    assert (
        runner.main(
            ["--extend-report", str(source), "--prompt-compare-step", "1", "--repeat", "4", "--output-dir", str(output)]
        )
        == 1
    )
    assert len(calls) == 4
    for label in ("before", "after"):
        records = runner._load_report_records(output / label)
        assert all(record["answer"] == "姓名" for record in records if record["repetition"] <= 3)
        for path in (source / label / "cases").glob("*.json"):
            assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
                (output / label / "cases" / path.name).read_text(encoding="utf-8")
            )
        assert json.loads((output / label / "metadata.json").read_text(encoding="utf-8"))["note"] == "評估紀錄"


def test_single_arm_extension_preserves_failures_and_can_be_extended_again(tmp_path, monkeypatch):
    source = tmp_path / "source"
    cases, _ = saved_report(source, failed=True)
    calls = []
    install_fake_runner(monkeypatch, calls)
    first = tmp_path / "first"
    assert runner.main(["--extend-report", str(source), "--output-dir", str(first)]) == 1
    assert len(calls) == 4  # Two new attempts for each case.
    records = runner._load_report_records(first)
    assert sum(bool(r["error"]) for r in records) == 2
    assert all(not r["token_usage"]["complete"] for r in records if r["repetition"] <= 3)
    calls.clear()
    second = tmp_path / "second"
    assert (
        runner.main(
            ["--extend-report", str(first), "--case", cases[0].id, "--repeat", "6", "--output-dir", str(second)]
        )
        == 1
    )
    assert len(calls) == 1
    reports = read_completed_reports(second)
    assert reports["production"].counts == {cases[0].id: 6, cases[1].id: 5}
    assert len(reports["production"].metadata["extensions"]) == 2


def test_extension_from_one_attempt_keeps_saved_files_and_labels_wall_time(tmp_path, monkeypatch):
    source = tmp_path / "source"
    cases, _ = saved_report(source, repetitions=1)
    calls = []
    install_fake_runner(monkeypatch, calls)
    output = tmp_path / "extended"
    assert (
        runner.main(
            [
                "--extend-report",
                str(source),
                "--case",
                cases[0].id,
                "--repeat",
                "3",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert len(calls) == 2
    assert read_completed_reports(output)["production"].counts == {cases[0].id: 3, cases[1].id: 1}
    assert (source / "cases" / f"{cases[0].id}.json").exists()
    assert (output / "cases" / f"{cases[0].id}--run-1.json").exists()
    assert "Extension wall time:" in (output / "summary.md").read_text()


@pytest.mark.parametrize("problem", ["outside-case", "existing-output", "missing-prompt-selector"])
def test_extension_rejects_an_invalid_scope_or_output_before_work(tmp_path, monkeypatch, problem):
    source = tmp_path / "source"
    saved_report(source, paired=True)
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    argv = ["--extend-report", str(source)]
    if problem != "missing-prompt-selector":
        argv.extend(["--prompt-compare-step", "1"])
    if problem == "outside-case":
        argv.extend(["--case", "ask-person-history"])
    elif problem == "existing-output":
        argv.extend(["--output-dir", str(source)])
    with pytest.raises(SystemExit, match="outside|must be new|original prompt comparison flags"):
        runner._selected_cases(argv)


def test_interrupted_extension_keeps_old_attempts_and_is_not_a_complete_report(tmp_path, monkeypatch):
    source = tmp_path / "source"
    saved_report(source)
    calls = []
    install_fake_runner(monkeypatch, calls)

    async def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted extension")

    monkeypatch.setattr(runner, "run_all", interrupted)
    output = tmp_path / "interrupted"
    with pytest.raises(RuntimeError, match="interrupted extension"):
        runner.main(["--extend-report", str(source), "--output-dir", str(output)])
    progress = json.loads((output / "progress.json").read_text())
    assert progress == {"status": "interrupted", "completed": 6, "expected": 10}
    assert len(runner._load_report_records(output)) == 6
    assert not (output / "summary.md").exists()


@pytest.mark.parametrize(
    "field",
    [
        "provider_model",
        "fail_fast",
        "sandbox_configuration",
        "cases_sha256",
        "prompt_sha256",
        "references_sha256",
        "fixtures_sha256",
        "attachments_sha256",
    ],
)
def test_changed_fingerprints_stop_before_any_provider_or_sandbox_work(tmp_path, monkeypatch, field):
    source = tmp_path / "source"
    saved_report(source)
    path = source / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata[field] = "changed"
    path.write_text(json.dumps(metadata))
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    monkeypatch.setattr(runner, "create_sandbox_factory", lambda _: pytest.fail("Must fail before provisioning"))
    with pytest.raises(SystemExit, match=field):
        runner.main(["--extend-report", str(source), "--output-dir", str(tmp_path / "new")])
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("corruption", ["interrupted", "duplicate", "missing", "trajectory", "unpaired"])
def test_incomplete_or_inconsistent_evidence_is_rejected(tmp_path, monkeypatch, corruption):
    source = tmp_path / "source"
    saved_report(source, paired=True)
    if corruption == "interrupted":
        (source / "progress.json").write_text(json.dumps({"status": "interrupted"}))
    elif corruption in {"duplicate", "missing"}:
        path = source / "before/results.jsonl"
        lines = path.read_text().splitlines()
        lines = lines + [lines[0]] if corruption == "duplicate" else lines[1:]
        path.write_text("\n".join(lines) + "\n")
    elif corruption == "trajectory":
        path = next((source / "before/cases").glob("*.json"))
        data = json.loads(path.read_text())
        data["seconds"] = 999
        path.write_text(json.dumps(data))
    else:
        path = source / "after/metadata.json"
        metadata = json.loads(path.read_text())
        metadata["case_ids"].reverse()
        path.write_text(json.dumps(metadata))
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    with pytest.raises(SystemExit, match="Cannot extend report"):
        runner._selected_cases(["--extend-report", str(source), "--prompt-compare-step", "1"])


def test_extension_inherits_cost_target_and_rejects_a_changed_target(tmp_path, monkeypatch):
    source = tmp_path / "source"
    saved_report(source, paired=True, cost_target=("total-tokens", 0.8))
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    args, _ = runner._selected_cases(["--extend-report", str(source), "--prompt-compare-step", "1"])
    assert (args.cost_metric, args.cost_ratio) == ("total-tokens", 0.8)
    with pytest.raises(SystemExit, match="cannot change the saved cost target"):
        runner._selected_cases(
            [
                "--extend-report",
                str(source),
                "--prompt-compare-step",
                "1",
                "--cost-metric",
                "total-tokens",
                "--cost-ratio",
                ".9",
            ]
        )


def test_extension_plan_validates_inputs_without_provider_work_or_output(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    cases, _ = saved_report(source, paired=True)
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    monkeypatch.setattr(runner, "create_sandbox_factory", lambda _: pytest.fail("Plan must not provision"))
    output = tmp_path / "new"
    assert (
        runner.main(
            [
                "--extend-report",
                str(source),
                "--prompt-compare-step",
                "1",
                "--case",
                cases[0].id,
                "--plan-only",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["new_attempts"] == 4
    assert plan["saved_attempts"] == 12
    assert plan["first_repetitions"] == {cases[0].id: 4}
    assert not output.exists()


@pytest.mark.parametrize("repetitions", [2, 3])
def test_extension_cannot_remove_or_repeat_saved_attempts(tmp_path, monkeypatch, repetitions):
    source = tmp_path / "source"
    saved_report(source)
    monkeypatch.setattr(runner.AiSettings, "from_env", settings)
    with pytest.raises(SystemExit, match="remove saved|add at least"):
        runner._selected_cases(["--extend-report", str(source), "--repeat", str(repetitions)])


def test_restored_record_keeps_timing_token_unknowns_and_provider_retries(tmp_path):
    _, runs = saved_report(tmp_path / "source")
    original = runs[0]
    saved = runner.CaseRun.from_saved(original.as_record(), original.as_trajectory())
    assert saved.as_record() == original.as_record()
    assert saved.as_trajectory() == original.as_trajectory()
    assert saved.token_usage.cached_prompt_tokens is None
    assert saved.sandbox_metrics == original.sandbox_metrics
    assert runner.summarize([saved]) == runner.summarize([original])


def test_extension_repetition_numbers_share_one_global_concurrency_limit():
    cases = [CASE_BY_ID["ask-people-count"]]
    provider = ConcurrentProvider()
    variants = (("before", runner.prompt_at_step(0)), ("after", runner.prompt_at_step(1)))
    runs = asyncio.run(
        runner.run_all(
            cases, settings(), provider, 4, _factory(), 5, prompt_variants=variants, repetition_starts={cases[0].id: 4}
        )
    )
    assert provider.max_active <= 4
    assert [(r.repetition, r.prompt_variant) for r in runs] == [
        (4, "after"),
        (4, "before"),
        (5, "before"),
        (5, "after"),
    ]
