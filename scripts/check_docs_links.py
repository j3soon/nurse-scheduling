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

"""Check built documentation links, repository references, and redirects offline."""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import tomllib

DOCS_HOSTS = {"nursescheduling.org", "dev.nursescheduling.org"}
REPOSITORY_PATH = "/j3soon/nurse-scheduling/blob/dev/"
URL = re.compile(r"https?://[^\s<>)\"']+")


class Page(HTMLParser):
    def __init__(self, text: str):
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        for name, value in attrs:
            if not value:
                continue
            if name == "id" or (tag == "a" and name == "name"):
                self.ids.add(value)
            elif name in {"href", "src"}:
                self.links.append(value)


def check_links(root: Path) -> list[str]:
    site = root / "site"
    if not (site / "index.html").is_file():
        return ["Build the docs with `zensical build --clean --strict` first."]
    redirects = tomllib.loads((root / "netlify.toml").read_text(encoding="utf-8")).get(
        "redirects", []
    )
    pages = {
        path: Page(path.read_text(encoding="utf-8")) for path in site.rglob("*.html")
    }
    sources = [
        root / name
        for name in (
            "README.md",
            "core/README.md",
            "web-frontend/README.md",
            "docker/README.md",
            "docs/README.md",
        )
    ]
    doc_sources = sorted((root / "docs/content").rglob("*.md"))
    sources += doc_sources
    doc_pages = {}
    for source in doc_sources:
        parts = source.relative_to(root / "docs/content").with_suffix("").parts
        if parts[-1] == "index":
            parts = parts[:-1]
        doc_pages[source.resolve()] = "/docs/" + "/".join((*parts, ""))
    errors: set[str] = set()

    def target_path(path: str) -> str:
        for _ in range(10):
            for redirect in redirects:
                old = redirect["from"]
                if old == path:
                    path = redirect["to"]
                    break
                if old.endswith("/*") and path.startswith(old[:-1]):
                    path = redirect["to"].replace(":splat", path[len(old) - 1 :])
                    break
            else:
                return path
        raise ValueError(f"redirect cycle for {path}")

    def check(url: str, owner: Path):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return
        path = unquote(parsed.path)
        if parsed.hostname == "github.com" and path.startswith(REPOSITORY_PATH):
            source = root / path.removeprefix(REPOSITORY_PATH)
            if not source.exists():
                errors.add(f"{owner.relative_to(root)}: missing repository file {path}")
            if source.resolve() not in doc_pages:
                return
            path = doc_pages[source.resolve()]
        elif parsed.hostname not in DOCS_HOSTS or not (
            path == "/docs" or path.startswith("/docs/")
        ):
            return
        if path == "/docs":
            path += "/"
        try:
            path = target_path(path)
        except ValueError as error:
            errors.add(str(error))
            return
        file = site / path.removeprefix("/docs/")
        if not file.is_file():
            file = file / "index.html"
        if not file.is_file():
            errors.add(f"{owner.relative_to(root)}: missing built target {path}")
        elif (
            parsed.fragment
            and not parsed.fragment.startswith("__")
            and file in pages
            and unquote(parsed.fragment) not in pages[file].ids
        ):
            errors.add(f"{owner.relative_to(root)}: missing anchor {url}")

    for file, page in pages.items():
        relative = file.relative_to(site).as_posix()
        page_url = "https://dev.nursescheduling.org/docs/" + relative
        for link in page.links:
            reference = urlsplit(link)
            destination = urljoin(page_url, link)
            if (
                not reference.scheme
                and not reference.netloc
                and not reference.path.startswith("/")
                and not urlsplit(destination).path.startswith("/docs/")
            ):
                errors.add(
                    f"{file.relative_to(root)}: relative link leaves docs: {link}"
                )
            else:
                check(destination, file)
    for source in sources:
        for url in URL.findall(source.read_text(encoding="utf-8")):
            check(url.rstrip(".,"), source)
    for redirect in redirects:
        target = redirect["to"].replace(":splat", "")
        if target.startswith("/docs/"):
            check("https://dev.nursescheduling.org" + target, root / "netlify.toml")
    return sorted(errors)


def main() -> int:
    errors = check_links(Path(__file__).resolve().parent.parent)
    if errors:
        print("\n".join(errors))
        return 1
    print("Built docs links, anchors, repository references, and redirects resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
