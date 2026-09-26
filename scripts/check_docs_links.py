#!/usr/bin/env python3
# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

"""Check deployed docs URLs in Markdown and redirect targets against a built site."""

import re
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DOCS_URL = re.compile(r"https://dev\.nursescheduling\.org/docs/[^\s)>'\"]+")
SOURCES = [
    ROOT / "README.md",
    ROOT / "core/README.md",
    ROOT / "web-frontend/README.md",
    ROOT / "docker/README.md",
    ROOT / "docs/README.md",
    *sorted((ROOT / "docs/content").rglob("*.md")),
]


def site_page(path: str) -> Path:
    return SITE / unquote(path).removeprefix("/docs/").strip("/") / "index.html"


def main() -> int:
    if not (SITE / "index.html").is_file():
        raise SystemExit("Build the docs with `zensical build --clean --strict` first.")

    errors = []
    for source in SOURCES:
        for url in DOCS_URL.findall(source.read_text(encoding="utf-8")):
            parsed = urlsplit(url.rstrip(".,"))
            page = site_page(parsed.path)
            if not page.is_file():
                errors.append(f"{source.relative_to(ROOT)}: missing page {parsed.path}")
            elif parsed.fragment and f'id="{unquote(parsed.fragment)}"' not in page.read_text(encoding="utf-8"):
                errors.append(f"{source.relative_to(ROOT)}: missing anchor {url}")

    redirects = tomllib.loads((ROOT / "netlify.toml").read_text(encoding="utf-8"))["redirects"]
    for redirect in redirects:
        target = redirect["to"].replace(":splat", "")
        if target.startswith("/docs/") and not site_page(target).is_file():
            errors.append(f"netlify.toml: missing redirect target {target}")

    if errors:
        print("\n".join(errors))
        return 1
    print("Deployed docs links, anchors, and redirect targets resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
