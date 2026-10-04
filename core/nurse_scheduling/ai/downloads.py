"""Validate the single generated ZIP allowed from a disposable workspace."""

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

import zlib
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

WORKSPACE_DOWNLOAD = "/workspace/download.zip"


def validate_download_zip(content: bytes, max_bytes: int) -> None:
    """Bound compressed and actual uncompressed bytes and check member integrity."""
    if len(content) > max_bytes:
        raise ValueError("The generated ZIP exceeds the download size limit.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > max_bytes:
                raise ValueError("The ZIP contents exceed the uncompressed size limit.")
            total = 0
            for item in archive.infolist():
                path = PurePosixPath(item.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("The ZIP must contain only relative file paths, without symbolic links.")
                with archive.open(item) as member:
                    while chunk := member.read(65536):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("The ZIP contents exceed the uncompressed size limit.")
    except (BadZipFile, RuntimeError, NotImplementedError, OSError, zlib.error) as exc:
        raise ValueError("The generated file is not a readable ZIP archive.") from exc
