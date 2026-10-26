"""Checks for bounded command tails and complete sandbox log files."""

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
import shlex
import subprocess
import sys

import pytest

from nurse_scheduling.ai.pi.bash import DEFAULT_MAX_BYTES, prepare_bash_output
from nurse_scheduling.ai.sandbox.command_output import MAX_TAIL_BYTES, OutputAccumulator
from nurse_scheduling.ai.sandbox.e2b import COMMAND_OUTPUT_SOURCE, _output_command, _prepare_output_report
from nurse_scheduling.ai.sandbox.e2b_commands import isolated_command


@pytest.mark.parametrize(
    "content",
    [
        "",
        "a\nb\n",
        "hello\n" * 3000,
        "é" * 100000,
        "prefix\n" + "x" * 1000000 + "\n",
        "start\n" * 40000 + "end\n",
        "x" * 1000000 + "\nlast line",
        "short\n" * 1999 + "z" * 50000,
    ],
    ids=[
        "empty",
        "two-lines",
        "over-line-limit",
        "long-multibyte-line",
        "long-middle-line",
        "over-both-limits",
        "long-first-line",
        "long-last-line",
    ],
)
@pytest.mark.parametrize("chunk_size", [4093, 65536])
def test_streamed_tail_matches_complete_pi_truncation(content, chunk_size):
    output = OutputAccumulator()
    encoded = content.encode()
    for offset in range(0, len(encoded), chunk_size):
        output.append(encoded[offset : offset + chunk_size])
        assert len(output.tail.encode()) <= MAX_TAIL_BYTES
    output.finish()
    assert _prepare_output_report(json.dumps(output.report())) == prepare_bash_output(content)


def test_split_utf8_and_invalid_bytes_match_one_decoded_stream():
    output = OutputAccumulator()
    raw = "你好é\n".encode() + b"\xff\xc3"
    for byte in raw:
        output.append(bytes([byte]))
    output.finish()
    assert _prepare_output_report(json.dumps(output.report())) == prepare_bash_output(raw.decode(errors="replace"))


@pytest.mark.skipif(sys.platform != "linux", reason="The sandbox command runs on Linux")
def test_large_command_keeps_the_full_log_and_only_returns_a_tail(tmp_path, monkeypatch):
    path = tmp_path / "large.log"
    script = (
        "import sys; chunk=b'x'*65536; "
        "exec('for _ in range(3200): sys.stdout.buffer.write(chunk)'); "
        "sys.stdout.flush(); sys.stderr.write('\\nfinished\\n')"
    )
    command = shlex.join([sys.executable, "-c", script])
    # The complete 200 MiB log cannot fit in this process's address space.
    bounded_source = (
        "import resource; resource.setrlimit(resource.RLIMIT_AS, (128*1024*1024, 128*1024*1024))\n"
        + COMMAND_OUTPUT_SOURCE
    )
    monkeypatch.setattr("nurse_scheduling.ai.sandbox.e2b.COMMAND_OUTPUT_SOURCE", bounded_source)
    captured = subprocess.run(
        ["bash", "-c", isolated_command(_output_command("run", str(path), command))],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert captured.returncode == 0, captured.stderr
    assert len(captured.stdout.encode()) < MAX_TAIL_BYTES + 1024
    prepared = _prepare_output_report(captured.stdout)
    assert prepared.truncation.truncated
    assert prepared.truncation.output_bytes <= DEFAULT_MAX_BYTES
    assert prepared.truncation.content.endswith("finished")
    assert path.stat().st_size > 200 * 1024 * 1024
    assert path.stat().st_size == prepared.truncation.total_bytes
    with path.open("rb") as log:
        assert log.read(16) == b"x" * 16
        log.seek(-10, 2)
        assert log.read() == b"\nfinished\n"


@pytest.mark.skipif(sys.platform != "linux", reason="The sandbox command runs on Linux")
def test_small_command_preserves_literal_shell_text_and_removes_its_log(tmp_path):
    path = tmp_path / "small.log"
    command = shlex.join(["printf", "%s\n", "literal $HOME `uname` and spaces"])
    captured = subprocess.run(
        ["bash", "-c", isolated_command(_output_command("run", str(path), command))],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert captured.returncode == 0, captured.stderr
    assert _prepare_output_report(captured.stdout).truncation.content == "literal $HOME `uname` and spaces\n"
    assert not path.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="The sandbox command runs on Linux")
def test_snapshot_recovers_partial_output_from_an_existing_log(tmp_path):
    path = tmp_path / "partial.log"
    content = b"line\n" * 40000
    path.write_bytes(content)
    snapshot = subprocess.run(
        ["bash", "-c", _output_command("snapshot", str(path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert snapshot.returncode == 0, snapshot.stderr
    assert _prepare_output_report(snapshot.stdout) == prepare_bash_output(content.decode())
    assert path.read_bytes() == content


@pytest.mark.skipif(sys.platform != "linux", reason="The sandbox command runs on Linux")
def test_snapshot_is_empty_when_timeout_stops_capture_before_log_creation(tmp_path):
    path = tmp_path / "not-created.log"
    snapshot = subprocess.run(
        ["bash", "-c", _output_command("snapshot", str(path))],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert snapshot.returncode == 0, snapshot.stderr
    assert _prepare_output_report(snapshot.stdout) == prepare_bash_output("")
    assert not path.exists()
