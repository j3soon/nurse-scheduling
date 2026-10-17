"""Build a complete session ZIP using bounded file reads and disk storage."""

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

import hashlib
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from starlette.responses import StreamingResponse

from .chat_export import build_saved_chat_export, escape_html
from .history import ChatHistory, _owner_hash

FILE_CHUNK_BYTES = 1024 * 1024


def _filename(value: str) -> str:
    name = PurePosixPath(value.replace("\\", "/")).name
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" .")[:180] or "attachment"


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _entry(path: str, milliseconds: int, *, compressed=True) -> ZipInfo:
    date = datetime.fromtimestamp(milliseconds / 1000, UTC)
    date = date.replace(year=max(1980, min(2107, date.year)))
    entry = ZipInfo(path, date.timetuple()[:6])
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    entry.compress_type = ZIP_DEFLATED if compressed else ZIP_STORED
    return entry


def _files(connection, session_id: str) -> list[dict]:
    rows = connection.execute(
        "SELECT id, kind, source_id, run_id, filename, media_type, octet_length(data), "
        "extract(epoch FROM created_at), extract(epoch FROM removed_at) FROM chat_files "
        "WHERE session_id = %s ORDER BY created_at, id",
        (session_id,),
    ).fetchall()
    return [
        {
            "id": str(identity),
            "kind": kind,
            "source_id": source,
            "run_id": run,
            "filename": filename,
            "media_type": media_type,
            "bytes": size,
            "created_at": round(float(created) * 1000),
            "removed_at": None if removed is None else round(float(removed) * 1000),
            "path": f"attachments/{_filename(kind)}/{identity}/{_filename(filename)}",
        }
        for identity, kind, source, run, filename, media_type, size, created, removed in rows
    ]


def read_file_chunk(connection, session_id: str, file_id: str, offset: int, length: int) -> bytes:
    row = connection.execute(
        "SELECT substring(data FROM %s FOR %s) FROM chat_files WHERE session_id = %s AND id = %s",
        (offset + 1, length, session_id, file_id),
    ).fetchone()
    if row is None:
        raise OSError("A session file disappeared during export")
    return row[0]


def _documents(snapshot, files):
    html = build_saved_chat_export(snapshot, "html")
    markdown = build_saved_chat_export(snapshot, "markdown")
    if files:
        rows, lines = [], []
        for file in files:
            label = (
                file["filename"] + " (" + file["kind"] + (", removed" if file["removed_at"] is not None else "") + ")"
            )
            url = quote(file["path"], safe="/")
            rows.append(f'<li><a href="{escape_html(url)}">{escape_html(label)}</a> ({file["bytes"]} bytes)</li>')
            # Escape labels so filenames cannot add Markdown links or formatting.
            md_label = re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", label)
            lines.append(f"- [{md_label}]({url}) ({file['bytes']} bytes)")
        index = (
            '<section class="proposal" aria-label="Session files"><h2>Session files</h2><ul>'
            + "".join(rows)
            + "</ul></section>\n"
        )
        html = html.replace("  </main>", "    " + index + "  </main>")
        markdown += "\n## Session files\n\n" + "\n".join(lines) + "\n"
    return html, markdown


def write_chat_archive(history: ChatHistory, session_id: str, output: BinaryIO, *, owner: str | None = None) -> None:
    """Write one snapshot without loading a whole file or the ZIP into memory."""
    with history._connect() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        row = connection.execute(
            "SELECT owner_hash, state, extract(epoch FROM expires_at) FROM chat_sessions "
            "WHERE id = %s AND expires_at > now()",
            (session_id,),
        ).fetchone()
        if row is None or (owner is not None and row[0] != _owner_hash(owner)):
            raise LookupError("Chat session not found.")
        snapshot = history.export_snapshot(session_id, snapshot_connection=connection)
        if snapshot is None:
            raise LookupError("Chat session not found.")
        snapshot = {**snapshot, "session_state": row[1], "expires_at": round(float(row[2]) * 1000)}
        files = _files(connection, session_id)
        at = max([snapshot["snapshot_at"], *(file["removed_at"] or file["created_at"] for file in files)])
        snapshot["snapshot_at"] = at
        html, markdown = _documents(snapshot, files)
        with ZipFile(output, "w", allowZip64=True) as archive:
            for filename, content in (
                ("chat.html", html.encode("utf-8")),
                ("chat.md", markdown.encode("utf-8")),
                ("chat.json", _json(snapshot)),
                ("schedule.yaml", row[1]["schedule_yaml"].encode("utf-8")),
            ):
                archive.writestr(_entry(filename, at), content)
            for file in files:
                digest = hashlib.sha256()
                compressed = file["media_type"].startswith("text/") or file["media_type"] in {
                    "application/json",
                    "application/yaml",
                }
                with archive.open(
                    _entry(file["path"], at, compressed=compressed), "w", force_zip64=True
                ) as destination:
                    offset = 0
                    while offset < file["bytes"]:
                        chunk = read_file_chunk(
                            connection, session_id, file["id"], offset, min(FILE_CHUNK_BYTES, file["bytes"] - offset)
                        )
                        if not chunk:
                            raise OSError("A session file is incomplete")
                        destination.write(chunk)
                        digest.update(chunk)
                        offset += len(chunk)
                file["sha256"] = digest.hexdigest()
            manifest = {
                "schema_version": 1,
                "session_id": session_id,
                "snapshot_at": at,
                "expires_at": snapshot["expires_at"],
                "files": files,
                "unfinished_runs": [run["id"] for run in snapshot["runs"] if run["status"] == "running"],
            }
            archive.writestr(_entry("manifest.json", at), _json(manifest))


def create_chat_archive(history: ChatHistory, session_id: str, *, owner: str | None = None) -> BinaryIO:
    """Return a disk-backed ZIP. The response owns and closes this temporary file."""
    output = tempfile.TemporaryFile(mode="w+b")  # noqa: SIM115 - ownership transfers to the response.
    try:
        write_chat_archive(history, session_id, output, owner=owner)
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise


class ChatArchiveResponse(StreamingResponse):
    """Stream a disk-backed archive and close it even when the client disconnects."""

    def __init__(self, archive: BinaryIO, filename: str) -> None:
        self.archive = archive
        size = archive.seek(0, 2)
        archive.seek(0)

        def chunks():
            while chunk := archive.read(FILE_CHUNK_BYTES):
                yield chunk

        super().__init__(
            chunks(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(size),
            },
        )

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.archive.close()
