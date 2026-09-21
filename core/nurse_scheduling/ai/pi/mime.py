"""Python port of Pi's supported-image MIME detection."""

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

# Adapted from Pi's packages/coding-agent/src/utils/mime.ts at
# e266507b606b9552fa277252644054afd4384b11. Pi's MIT license is in LICENSE.
# This code is mostly AI generated.

IMAGE_TYPE_DETECTION_BYTES = 4_100


def detect_supported_image_mime_type(content: bytes) -> str | None:
    """Recognize exactly the image formats accepted by Pi's read tool."""
    buffer = content[:IMAGE_TYPE_DETECTION_BYTES]
    if buffer.startswith(b"\xff\xd8\xff"):
        return None if len(buffer) > 3 and buffer[3] == 0xF7 else "image/jpeg"
    if buffer.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png" if _is_png(buffer) and not _is_animated_png(buffer) else None
    if buffer.startswith(b"GIF"):
        return "image/gif"
    if buffer.startswith(b"RIFF") and buffer[8:12] == b"WEBP":
        return "image/webp"
    if buffer.startswith(b"BM") and _is_bmp(buffer):
        return "image/bmp"
    return None


def _is_png(buffer: bytes) -> bool:
    return len(buffer) >= 16 and int.from_bytes(buffer[8:12], "big") == 13 and buffer[12:16] == b"IHDR"


def _is_animated_png(buffer: bytes) -> bool:
    offset = 8
    while offset + 8 <= len(buffer):
        chunk_length = int.from_bytes(buffer[offset : offset + 4], "big")
        chunk_type = buffer[offset + 4 : offset + 8]
        if chunk_type == b"acTL":
            return True
        if chunk_type == b"IDAT":
            return False
        next_offset = offset + 8 + chunk_length + 4
        if next_offset <= offset or next_offset > len(buffer):
            return False
        offset = next_offset
    return False


def _is_bmp(buffer: bytes) -> bool:
    if len(buffer) < 26:
        return False
    declared_size = int.from_bytes(buffer[2:6], "little")
    pixel_offset = int.from_bytes(buffer[10:14], "little")
    dib_size = int.from_bytes(buffer[14:18], "little")
    if declared_size and declared_size < 26:
        return False
    if pixel_offset < 14 + dib_size or (declared_size and pixel_offset >= declared_size):
        return False
    if dib_size == 12:
        planes = int.from_bytes(buffer[22:24], "little")
        bits_per_pixel = int.from_bytes(buffer[24:26], "little")
    elif 40 <= dib_size <= 124 and len(buffer) >= 30:
        planes = int.from_bytes(buffer[26:28], "little")
        bits_per_pixel = int.from_bytes(buffer[28:30], "little")
    else:
        return False
    return planes == 1 and bits_per_pixel in {1, 4, 8, 16, 24, 32}
