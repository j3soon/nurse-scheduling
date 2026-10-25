"""Stream command output to sandbox storage and retain a bounded UTF-8 tail."""

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

# This code is mostly AI generated.

import codecs
import json
import subprocess
import sys
from pathlib import Path

MAX_TAIL_BYTES = 100 * 1024
CHUNK_BYTES = 64 * 1024


class OutputAccumulator:
    """Count complete output without retaining more than a small tail."""

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.tail = ""
        self.total_bytes = 0
        self.completed_lines = 0
        self.last_line_bytes = 0

    def append(self, data):
        self._append_text(self.decoder.decode(data))

    def finish(self):
        self._append_text(self.decoder.decode(b"", final=True))

    def _append_text(self, text):
        encoded = text.encode("utf-8")
        self.total_bytes += len(encoded)
        newlines = text.count("\n")
        self.completed_lines += newlines
        if newlines:
            self.last_line_bytes = len(text.rsplit("\n", 1)[-1].encode("utf-8"))
        else:
            self.last_line_bytes += len(encoded)
        self.tail = (self.tail + text).encode("utf-8")[-MAX_TAIL_BYTES:].decode("utf-8", errors="ignore")

    def report(self):
        return {
            "tail": self.tail,
            "total_bytes": self.total_bytes,
            "total_lines": self.completed_lines + (1 if self.last_line_bytes else 0),
            "last_line_bytes": self.last_line_bytes,
        }


def main():
    mode, path = sys.argv[1:3]
    output = OutputAccumulator()
    exit_code = 0
    if mode == "run":
        with (
            open(path, "xb", buffering=0) as log,
            subprocess.Popen(
                ["/bin/bash", "-c", sys.argv[3]],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            ) as command,
        ):
            while chunk := command.stdout.read1(CHUNK_BYTES):
                log.write(chunk)
                output.append(chunk)
            exit_code = command.wait()
    elif mode == "snapshot":
        try:
            with open(path, "rb") as log:
                while chunk := log.read(CHUNK_BYTES):
                    output.append(chunk)
        except FileNotFoundError:
            # Cleanup can stop capture before it creates the log.
            pass
    else:
        raise ValueError("Unknown command output mode")
    output.finish()
    print(json.dumps(output.report(), ensure_ascii=False))
    if output.total_bytes <= 50 * 1024 and output.report()["total_lines"] <= 2000:
        Path(path).unlink(missing_ok=True)
    sys.exit(exit_code if exit_code >= 0 else 128 - exit_code)


if __name__ == "__main__":
    main()
