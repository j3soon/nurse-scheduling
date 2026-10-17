"""Export a saved session ZIP through the same writer used by the AI service."""

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

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import psycopg

from .chat_archive import create_chat_archive, write_chat_archive
from .history import ChatHistory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", type=UUID)
    parser.add_argument("output", help="Destination .zip path, or - for binary stdout")
    args = parser.parse_args()
    database_url = os.environ.get("AI_HISTORY_POSTGRES_URL", "").strip()
    if not database_url:
        parser.error("AI_HISTORY_POSTGRES_URL is required")
    if args.output != "-" and not args.output.endswith(".zip"):
        parser.error("Choose a .zip output path")
    history = ChatHistory(database_url)
    temporary = None
    try:
        if args.output == "-":
            with create_chat_archive(history, str(args.session_id)) as archive:
                shutil.copyfileobj(archive, sys.stdout.buffer, 1024 * 1024)
        else:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w+b", dir=output.parent, prefix=".chat-export-", delete=False
            ) as archive:
                temporary = Path(archive.name)
                write_chat_archive(history, str(args.session_id), archive)
            temporary.replace(output)
            temporary = None
    except (psycopg.Error, OSError, LookupError):
        parser.exit(1, "Could not export the saved chat. Check the session, PostgreSQL access, and output path.\n")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
