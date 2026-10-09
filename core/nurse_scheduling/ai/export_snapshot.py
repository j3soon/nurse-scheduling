"""Read a saved chat snapshot for the shared frontend export formatter."""

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
import json
import os
import sys
from uuid import UUID

import psycopg

from .history import ChatHistory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", type=UUID)
    args = parser.parse_args()
    database_url = os.environ.get("AI_HISTORY_POSTGRES_URL", "").strip()
    if not database_url:
        parser.error("AI_HISTORY_POSTGRES_URL is required")
    try:
        snapshot = ChatHistory(database_url).export_snapshot(str(args.session_id))
    except psycopg.Error:
        parser.exit(1, "Could not read the saved chat snapshot. Check PostgreSQL access.\n")
    if snapshot is None:
        parser.exit(1, "Saved chat session not found.\n")
    json.dump(snapshot, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
