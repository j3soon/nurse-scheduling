"""Render current chat HTML and compare browser screenshots for the E2E suite."""

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

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("render")
    compare = subparsers.add_parser("compare")
    compare.add_argument("frontend", type=Path)
    compare.add_argument("export", type=Path)
    compare.add_argument("difference", type=Path)
    args = parser.parse_args()
    if args.action == "render":
        from nurse_scheduling.ai.chat_export import build_saved_chat_export

        print(build_saved_chat_export(json.load(sys.stdin), "html"))
        return

    from PIL import Image, ImageChops, ImageOps

    with Image.open(args.frontend) as frontend, Image.open(args.export) as exported:
        if frontend.size != exported.size:
            print(f"Different dimensions: {frontend.size} vs {exported.size}")
            return
        difference = ImageChops.difference(frontend.convert("RGB"), exported.convert("RGB"))
        # Separate browser surfaces can round antialiased corners by one RGB level.
        # The browser test also compares computed styles exactly.
        if max(channel[1] for channel in difference.getextrema()) <= 1:
            print("identical")
        else:
            ImageOps.autocontrast(difference).save(args.difference)
            print(f"Different pixels in {difference.getbbox()}")


if __name__ == "__main__":
    main()
