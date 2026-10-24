"""Verify bounded, read-only administrator views of saved user prompts."""

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

import io
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from nurse_scheduling.ai.provider import TokenUsage
from nurse_scheduling.ai.recent_prompts import _main, _preview, print_recent_prompts, read_recent_prompts
from nurse_scheduling.ai.transcript import AssistantMessage, UserMessage

from .test_ai_history import postgres_history, session_state, uninitialized_postgres_history

__all__ = ["postgres_history", "uninitialized_postgres_history"]
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "recent_ai_prompts.sh"


def _bash_executable(*, windows: bool) -> str | None:
    candidates = []
    if windows and (git := shutil.which("git")):
        # Git's wrapper configures MSYS and PATH. Windows' bash.exe can be a WSL launcher.
        candidates.extend(parent / "bin" / "bash.exe" for parent in Path(git).resolve().parents)
    if bash := shutil.which("bash"):
        candidates.append(Path(bash))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            version = subprocess.run(
                [str(candidate), "--version"],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if version.returncode == 0 and version.stdout.startswith("GNU bash"):
            return str(candidate)
    return None


def seed_session(history, position, *, kind="foreground", prompts=1, text=None, session_id=None):
    session_id = session_id or str(uuid4())
    run_id, owner = (str(uuid4()) for _ in range(2))
    state = session_state(owner)
    history.start_run(
        run_id,
        session_id,
        state,
        text or f"Question {position}",
        0,
        model="test-model",
        attachment_count=0,
        kind=kind,
    )
    history.finish_run(
        run_id,
        "completed",
        None,
        TokenUsage(123, 45, 168),
        session_id=session_id,
        state=state,
        entries=[
            *((index, run_id, UserMessage(f"Steering {index}: " + "字" * 400)) for index in range(1, prompts)),
            (prompts, run_id, AssistantMessage("ASSISTANT_SECRET")),
        ],
    )
    with history._connect() as connection:
        connection.execute(
            "UPDATE chat_sessions SET created_at = %s WHERE id = %s", (BASE_TIME + timedelta(days=position), session_id)
        )
        connection.execute(
            "UPDATE chat_session_entries SET created_at = %s WHERE session_id = %s",
            (BASE_TIME + timedelta(days=position, hours=1), session_id),
        )
    return session_id, run_id


def database_url(history):
    with history._connect() as connection:
        info = connection.info
        return make_conninfo(info.dsn, password=info.password) if info.password else info.dsn


def test_recent_prompts_order_ties_bounds_and_read_only(postgres_history):
    older, older_run = seed_session(postgres_history, 1, prompts=3)
    newer, _ = seed_session(postgres_history, 2)
    seed_session(postgres_history, 3, kind="background")
    # Activity, rather than session creation, determines which session is recent.
    with postgres_history._connect() as connection:
        connection.execute(
            "UPDATE chat_session_entries SET created_at = %s WHERE session_id = %s",
            (BASE_TIME + timedelta(days=4), older),
        )
        connection.execute("UPDATE chat_runs SET usage = NULL WHERE id = %s", (older_run,))
    with postgres_history._connect() as connection:
        connection.row_factory = dict_row
        rows = read_recent_prompts(connection, sessions=2, prompts=2, chars=13)
        assert [row["id"] for row in rows] == [older, newer]
        assert [prompt["preview"] for prompt in rows[0]["prompts"]] == ["Steering 2: 字", "Steering 1: 字"]
        assert rows[0]["prompts"][0]["prompt_count"] == 3
        assert rows[0]["prompts"][0]["chars"] == 412
        assert connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute("DELETE FROM chat_sessions")
    output = io.StringIO()
    print_recent_prompts(rows, output)
    rendered = output.getvalue()
    assert "ASSISTANT_SECRET" not in rendered
    assert "run tokens in=? out=?" in rendered
    assert "run tokens in=123 out=45" in rendered
    assert "Steering 2: 字…" in rendered
    assert "UTC" in rendered


def test_cli_session_limit_breaks_timestamp_ties_by_run_admission(postgres_history, monkeypatch, capsys):
    older, _ = seed_session(postgres_history, 1, session_id="ffffffff-ffff-4fff-bfff-ffffffffffff")
    newer, _ = seed_session(postgres_history, 1, session_id="00000000-0000-4000-8000-000000000001")
    assert older > newer
    monkeypatch.setenv("AI_HISTORY_POSTGRES_URL", database_url(postgres_history))
    monkeypatch.setattr(sys, "argv", ["recent_prompts", "--sessions", "1"])
    _main()
    output = capsys.readouterr().out
    assert output.startswith(newer)
    assert older not in output


def test_cli_defaults_overrides_and_select_only_role(postgres_history):
    sessions = [seed_session(postgres_history, position, prompts=6) for position in range(17)]
    url = database_url(postgres_history)
    role = "prompt_reader_" + uuid4().hex
    with postgres_history._connect() as connection:
        schema = connection.execute("SELECT current_schema()").fetchone()[0]
        connection.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role))
        )
        connection.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(role)
            )
        )
    options = conninfo_to_dict(url).get("options", "")
    env = {**os.environ, "AI_HISTORY_POSTGRES_URL": make_conninfo(url, options=f"{options} -c role={role}")}
    try:
        for flags, session_limit, prompt_limit in [
            ((), 15, 5),
            (("--sessions", "2", "--prompts", "2", "--chars", "16"), 2, 2),
        ]:
            command = [sys.executable, "-m", "nurse_scheduling.ai.recent_prompts"]
            if flags and os.name != "nt" and shutil.which("bash"):
                command = ["bash", str(SCRIPT)]
            result = subprocess.run(
                [*command, *flags],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=15,
            )
            assert result.returncode == 0, result.stderr
            lines = result.stdout.splitlines()
            assert len([line for line in lines if not line.startswith("  ")]) == session_limit
            assert len([line for line in lines if line.startswith("  ")]) == session_limit * prompt_limit
            assert lines[0].startswith(sessions[-1][0])
            assert f"prompts {prompt_limit}/6" in lines[0]
            assert "ASSISTANT_SECRET" not in result.stdout
            previews = [line.split(" | ")[-1] for line in lines if line.startswith("  ")]
            assert all(len(preview) == (301 if not flags else 17) for preview in previews)
    finally:
        with postgres_history._connect() as connection:
            connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_background_activity_and_empty_sessions_are_not_user_prompts(postgres_history):
    session, _ = seed_session(postgres_history, 1)
    background = str(uuid4())
    postgres_history.start_run(
        background,
        session,
        session_state("owner"),
        "AUTOMATIC_OPTIMIZER_PROMPT",
        10,
        model="model",
        attachment_count=0,
        kind="background",
    )
    postgres_history.save_session(str(uuid4()), session_state("owner"))
    with postgres_history._connect() as connection:
        connection.row_factory = dict_row
        rows = read_recent_prompts(connection, sessions=15, prompts=5, chars=300)
    assert len(rows) == 1
    assert rows[0]["prompts"][0]["preview"] == "Question 1"
    assert rows[0]["prompts"][0]["prompt_count"] == 1


def test_empty_database(postgres_history):
    with postgres_history._connect() as connection:
        connection.row_factory = dict_row
        rows = read_recent_prompts(connection, sessions=15, prompts=5, chars=300)
    output = io.StringIO()
    print_recent_prompts(rows, output)
    assert output.getvalue() == "No saved user prompts found.\n"


def test_terminal_preview_removes_control_characters():
    assert _preview("第一行\n\t第二行\x1b[2J\u202eevil") == "第一行 第二行 [2J evil"


@pytest.mark.parametrize("flag,value", [("--sessions", "0"), ("--prompts", "-1"), ("--chars", "bad")])
def test_cli_rejects_invalid_limits_before_connecting(monkeypatch, capsys, flag, value):
    monkeypatch.setattr(sys, "argv", ["recent_prompts", flag, value])
    with pytest.raises(SystemExit) as result:
        _main()
    assert result.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_requires_database_url(monkeypatch, capsys):
    monkeypatch.delenv("AI_HISTORY_POSTGRES_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["recent_prompts"])
    with pytest.raises(SystemExit) as result:
        _main()
    assert result.value.code == 2
    assert "AI_HISTORY_POSTGRES_URL is required" in capsys.readouterr().err


def test_cli_logs_database_failure_and_preserves_exit_message(monkeypatch, capsys, caplog):
    monkeypatch.setenv("AI_HISTORY_POSTGRES_URL", "postgresql://localhost/test")
    monkeypatch.setattr(sys, "argv", ["recent_prompts"])
    error = psycopg.OperationalError("database unavailable")

    def fail_connect(*args, **kwargs):
        raise error

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    with pytest.raises(SystemExit) as result:
        _main()
    assert result.value.code == 1
    assert capsys.readouterr().err == "Could not read saved user prompts: database unavailable\n"
    record = next(record for record in caplog.records if record.message == "Could not read saved user prompts")
    assert record.exc_info[1] is error


def test_bash_discovery_prefers_git_bash_to_windows_launcher(tmp_path, monkeypatch):
    git = tmp_path / "Git" / "cmd" / "git.exe"
    bash = git.parents[1] / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    monkeypatch.setattr(shutil, "which", lambda command: str(git) if command == "git" else "windows-bash.exe")
    monkeypatch.setattr(
        subprocess, "run", lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, "GNU bash", "")
    )
    assert _bash_executable(windows=True) == str(bash.resolve())


def test_bash_discovery_rejects_unusable_windows_launcher(tmp_path, monkeypatch):
    launcher = tmp_path / "bash.exe"
    launcher.touch()
    monkeypatch.setattr(shutil, "which", lambda command: str(launcher) if command == "bash" else None)
    monkeypatch.setattr(
        subprocess, "run", lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, "W\0S\0L\0", "")
    )
    assert _bash_executable(windows=True) is None


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_shell_help_needs_no_database_or_docker(tmp_path, line_ending):
    bash = _bash_executable(windows=os.name == "nt")
    if bash is None:
        pytest.skip("A working Bash interpreter is not installed")
    script = tmp_path / SCRIPT.name
    script.write_bytes(SCRIPT.read_text(encoding="utf-8").replace("\n", line_ending).encode("utf-8"))
    result = subprocess.run(
        [bash, "-s", "--", "--help"],
        # Read normalized text and send bytes so Windows does not translate LF back to CRLF.
        input=script.read_text(encoding="utf-8").encode("utf-8"),
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert b"15 sessions, 5 prompts" in result.stdout


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Requires a POSIX shell")
def test_shell_forwards_compose_configuration_and_limits(tmp_path, monkeypatch):
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    docker.chmod(0o755)
    monkeypatch.delenv("AI_HISTORY_POSTGRES_URL", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    environment_file = tmp_path / ".env.staging"
    environment_file.touch()
    monkeypatch.setenv("AI_ENV_FILE", str(environment_file))
    monkeypatch.setenv("AI_COMPOSE_FILE", "docker/compose.backend.memory.yml")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--sessions", "2", "--prompts", "3", "--chars", "20"],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert result.stdout.splitlines() == [
        "compose",
        "--env-file",
        str(environment_file),
        "-f",
        "docker/compose.backend.memory.yml",
        "exec",
        "-T",
        "ai",
        "python",
        "-m",
        "nurse_scheduling.ai.recent_prompts",
        "--sessions",
        "2",
        "--prompts",
        "3",
        "--chars",
        "20",
    ]
    assert str(environment_file) in result.stderr
    assert "Falling back" not in result.stderr


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Requires a POSIX shell")
@pytest.mark.parametrize(
    "files,explicit,selected,fallback",
    [
        ((".env", ".env.staging"), None, ".env", False),
        ((".env",), None, ".env", False),
        ((".env.staging",), None, ".env.staging", True),
        ((".env", ".env.staging", "custom.env"), "custom.env", "custom.env", False),
        ((".env.staging",), "missing.env", None, False),
        ((), None, None, False),
    ],
    ids=["prefer-default", "default-only", "staging-fallback", "explicit-file", "explicit-missing", "no-files"],
)
def test_shell_environment_selection(tmp_path, monkeypatch, files, explicit, selected, fallback):
    # Run a copy so environment selection never touches the deployment's real secrets.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    configuration = tmp_path / "docker"
    configuration.mkdir()
    for filename in files:
        (configuration / filename).touch()
    docker = tmp_path / "docker-stub"
    docker.mkdir()
    executable = docker / "docker"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(docker) + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("AI_HISTORY_POSTGRES_URL", raising=False)
    monkeypatch.delenv("AI_ENV_FILE", raising=False)
    monkeypatch.delenv("AI_COMPOSE_FILE", raising=False)
    if explicit:
        monkeypatch.setenv("AI_ENV_FILE", str(configuration / explicit))
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, check=False, text=True, encoding="utf-8", timeout=5
    )
    if selected is None:
        assert result.returncode == 2
        assert result.stdout == ""
        assert "Environment file not found" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[2] == str(configuration / selected)
        assert str(configuration / selected) in result.stderr
    assert ("Falling back" in result.stderr) is fallback
