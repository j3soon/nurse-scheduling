"""Show recent saved user prompts without modifying PostgreSQL."""

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
import logging
import os
import sys
from datetime import UTC, datetime
from typing import TextIO

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from ..sentry import flush_sentry, init_sentry
from ..version import get_app_version

logger = logging.getLogger(__name__)


def read_recent_prompts(connection, *, sessions: int, prompts: int, chars: int) -> list[dict]:
    """Read bounded previews through a consistent, database-enforced read-only snapshot."""
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    recent = connection.execute(
        "SELECT s.id::text, s.created_at, latest.created_at AS last_prompt_at "
        "FROM chat_sessions s JOIN LATERAL ("
        "SELECT e.created_at, r.sequence FROM chat_session_entries e JOIN chat_runs r ON r.id = e.run_id "
        "WHERE e.session_id = s.id AND e.type = 'user' AND r.kind = 'foreground' "
        "ORDER BY e.created_at DESC, e.seq DESC LIMIT 1"
        ") latest ON true ORDER BY latest.created_at DESC, latest.sequence DESC LIMIT %s",
        (sessions,),
    ).fetchall()
    for session in recent:
        session["prompts"] = connection.execute(
            "SELECT e.created_at, left(e.payload->>'text', %s) AS preview, "
            "char_length(e.payload->>'text') AS chars, count(*) OVER () AS prompt_count, "
            "r.status, r.usage->>'prompt_tokens' AS input_tokens, "
            "r.usage->>'completion_tokens' AS output_tokens "
            "FROM chat_session_entries e JOIN chat_runs r ON r.id = e.run_id "
            "WHERE e.session_id = %s AND e.type = 'user' AND r.kind = 'foreground' "
            "ORDER BY e.created_at DESC, e.seq DESC LIMIT %s",
            (chars, session["id"], prompts),
        ).fetchall()
    return recent


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _preview(text: str) -> str:
    # Keep stored control characters from changing the administrator's terminal.
    return " ".join("".join(character if character.isprintable() else " " for character in text).split())


def print_recent_prompts(recent: list[dict], output: TextIO) -> None:
    if not recent:
        print("No saved user prompts found.", file=output)
    for session in recent:
        prompts = session["prompts"]
        print(
            f"{session['id']} | latest {_timestamp(session['last_prompt_at'])} | "
            f"created {_timestamp(session['created_at'])} | prompts {len(prompts)}/{prompts[0]['prompt_count']}",
            file=output,
        )
        for prompt in prompts:
            preview = _preview(prompt["preview"] or "")
            if prompt["chars"] > len(prompt["preview"] or ""):
                preview += "…"
            input_tokens = prompt["input_tokens"] if prompt["input_tokens"] is not None else "?"
            output_tokens = prompt["output_tokens"] if prompt["output_tokens"] is not None else "?"
            print(
                f"  {_timestamp(prompt['created_at'])} | {prompt['status']} | "
                f"run tokens in={input_tokens} out={output_tokens} | user chars={prompt['chars']} | {preview}",
                file=output,
            )


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Use a positive integer")
    return number


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--sessions", type=_positive_int, default=15, help="Maximum recent sessions")
    parser.add_argument("--prompts", type=_positive_int, default=5, help="Maximum recent user prompts per session")
    parser.add_argument("--chars", type=_positive_int, default=300, help="Maximum characters per prompt preview")
    args = parser.parse_args()
    database_url = os.environ.get("AI_HISTORY_POSTGRES_URL", "").strip()
    if not database_url:
        parser.error("AI_HISTORY_POSTGRES_URL is required")
    try:
        options = conninfo_to_dict(database_url).get("options", "")
        with psycopg.connect(
            database_url,
            connect_timeout=5,
            options=f"{options} -c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=5000",
            row_factory=dict_row,
        ) as connection:
            recent = read_recent_prompts(connection, **vars(args))
        print_recent_prompts(recent, sys.stdout)
    except psycopg.Error as exc:
        logger.exception("Could not read saved user prompts")
        parser.exit(1, f"Could not read saved user prompts: {exc}\n")


def main() -> None:
    init_sentry(get_app_version(), app="ai-recent-prompts")
    try:
        _main()
    finally:
        flush_sentry()


if __name__ == "__main__":
    main()
