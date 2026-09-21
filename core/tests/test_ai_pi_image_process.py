"""Tests for the Python port of Pi's image processing behavior."""

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
import random

from PIL import Image

from nurse_scheduling.ai.pi.image_process import (
    MAX_IMAGE_BASE64_BYTES,
    ProcessedImage,
    _resize_image,
    process_image,
)


def test_pi_image_process_passes_small_supported_images_through():
    image = Image.new("RGB", (64, 48), (120, 160, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()

    result = process_image(data, "image/png")

    assert isinstance(result, ProcessedImage)
    assert result.data == data
    assert result.media_type == "image/png"
    assert result.hints == ()


def test_pi_image_process_conversion_hint_uses_the_final_encoding():
    small = Image.new("RGB", (10, 10), (200, 40, 40))
    tiff = io.BytesIO()
    small.save(tiff, format="TIFF")

    result = process_image(tiff.getvalue(), "image/tiff")

    assert isinstance(result, ProcessedImage)
    assert result.media_type == "image/png"
    assert result.hints == ("[Image converted from image/tiff to image/png].",)


def test_pi_image_process_reports_jpeg_conversion_after_resize():
    # Random noise stays incompressible as PNG, so the resized encoding falls
    # back to JPEG. Pi reports the final encoding in the conversion hint.
    width = height = 1200
    noise = Image.frombytes("RGB", (width, height), random.Random(0).randbytes(width * height * 3))
    tiff = io.BytesIO()
    noise.save(tiff, format="TIFF")

    result = process_image(tiff.getvalue(), "image/tiff")

    assert isinstance(result, ProcessedImage)
    assert result.media_type == "image/jpeg"
    assert result.hints[0] == "[Image converted from image/tiff to image/jpeg]."
    assert "original 1200x1200, displayed at 1200x1200" in result.hints[1]
    assert ((len(result.data) + 2) // 3) * 4 < MAX_IMAGE_BASE64_BYTES


def test_pi_image_resize_rounds_target_dimensions_like_math_round():
    # 1021 * 2000 / 4000 is exactly 510.5: Math.round gives 511, while
    # Python's banker's round() gives 510.
    source = Image.new("RGB", (4000, 1021), (30, 120, 90))

    _data, media_type, width, height = _resize_image(source, 4000, 1021)

    assert (width, height) == (2000, 511)
    assert media_type in {"image/png", "image/jpeg"}
