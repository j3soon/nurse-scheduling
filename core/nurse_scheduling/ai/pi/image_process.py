"""Python port of Pi's model-facing image processing behavior."""

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

# Adapted from Pi's packages/coding-agent/src/utils/image-process.ts and
# image-resize-core.ts at e266507b606b9552fa277252644054afd4384b11.
# Pi's MIT license is in LICENSE.
# This code is mostly AI generated.

import math
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

MAX_IMAGE_DIMENSION = 2_000
MAX_SOURCE_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_BASE64_BYTES = int(4.5 * 1_024 * 1_024)
CONVERSION_FAILURE = "[Image omitted: could not be converted to a supported inline image format.]"
RESIZE_FAILURE = "[Image omitted: could not be resized below the inline image size limit.]"


@dataclass(frozen=True)
class ProcessedImage:
    """One provider-ready image and any model-facing processing hints."""

    data: bytes
    media_type: str
    hints: tuple[str, ...]


@dataclass(frozen=True)
class ImageProcessFailure:
    """The model-facing omission message returned by Pi."""

    message: str


def process_image(content: bytes, media_type: str) -> ProcessedImage | ImageProcessFailure:
    """Normalize and resize an image using Pi's defaults."""
    base_media_type = media_type.partition(";")[0].strip().lower()
    normalized_types = {
        "image/png": "image/png",
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "image/gif": "image/gif",
        "image/webp": "image/webp",
    }
    normalized_type = normalized_types.get(base_media_type)
    converted_from: str | None = None
    normalized_data = content
    if normalized_type is None:
        normalized_data = _convert_to_png(content)
        if normalized_data is None:
            return ImageProcessFailure(CONVERSION_FAILURE)
        normalized_type = "image/png"
        converted_from = base_media_type

    try:
        with Image.open(BytesIO(normalized_data)) as opened:
            # Unlike Pi, reject oversized source images before Pillow decodes them.
            if opened.width * opened.height > MAX_SOURCE_IMAGE_PIXELS:
                return ImageProcessFailure(RESIZE_FAILURE)
            opened.load()
            source = ImageOps.exif_transpose(opened)
            original_width, original_height = source.size
            hints: list[str] = []

            base64_bytes = ((len(normalized_data) + 2) // 3) * 4
            if (
                original_width <= MAX_IMAGE_DIMENSION
                and original_height <= MAX_IMAGE_DIMENSION
                and base64_bytes < MAX_IMAGE_BASE64_BYTES
            ):
                # Pi reports the final encoding in the conversion hint. For
                # an unresized image that is the normalized type.
                if converted_from is not None and converted_from != normalized_type:
                    hints.append(f"[Image converted from {converted_from} to {normalized_type}].")
                return ProcessedImage(normalized_data, normalized_type, tuple(hints))

            resized = _resize_image(source, original_width, original_height)
            if resized is None:
                return ImageProcessFailure(RESIZE_FAILURE)
            data, result_type, width, height = resized
            if converted_from is not None and converted_from != result_type:
                hints.append(f"[Image converted from {converted_from} to {result_type}].")
            scale = original_width / width
            hints.append(
                f"[Image: original {original_width}x{original_height}, displayed at {width}x{height}. "
                f"Multiply coordinates by {scale:.2f} to map to original image.]"
            )
            return ProcessedImage(data, result_type, tuple(hints))
    except (Image.DecompressionBombError, OSError, ValueError):
        return ImageProcessFailure(RESIZE_FAILURE)


def _convert_to_png(content: bytes) -> bytes | None:
    """Convert a provider-unsupported image to PNG as Pi does before resizing."""
    try:
        with Image.open(BytesIO(content)) as opened:
            if opened.width * opened.height > MAX_SOURCE_IMAGE_PIXELS:
                return None
            opened.load()
            source = ImageOps.exif_transpose(opened)
            output = BytesIO()
            source.save(output, format="PNG")
            return output.getvalue()
    except (Image.DecompressionBombError, OSError, ValueError):
        return None


def _resize_image(
    source: Image.Image,
    original_width: int,
    original_height: int,
) -> tuple[bytes, str, int, int] | None:
    width, height = original_width, original_height
    if width > MAX_IMAGE_DIMENSION:
        # Match Pi's Math.round: round halves up, unlike Python's banker's round.
        height = math.floor(height * MAX_IMAGE_DIMENSION / width + 0.5)
        width = MAX_IMAGE_DIMENSION
    if height > MAX_IMAGE_DIMENSION:
        width = math.floor(width * MAX_IMAGE_DIMENSION / height + 0.5)
        height = MAX_IMAGE_DIMENSION

    while True:
        resized = source.resize((width, height), Image.Resampling.LANCZOS)
        candidates: list[tuple[bytes, str]] = []
        png = BytesIO()
        resized.save(png, format="PNG")
        candidates.append((png.getvalue(), "image/png"))
        rgb = resized if resized.mode in {"RGB", "L"} else resized.convert("RGB")
        for quality in (80, 85, 70, 55, 40):
            jpeg = BytesIO()
            rgb.save(jpeg, format="JPEG", quality=quality)
            candidates.append((jpeg.getvalue(), "image/jpeg"))
        for data, candidate_type in candidates:
            if ((len(data) + 2) // 3) * 4 < MAX_IMAGE_BASE64_BYTES:
                return data, candidate_type, width, height
        if width == 1 and height == 1:
            return None
        next_width = 1 if width == 1 else max(1, int(width * 0.75))
        next_height = 1 if height == 1 else max(1, int(height * 0.75))
        if (next_width, next_height) == (width, height):
            return None
        width, height = next_width, next_height
