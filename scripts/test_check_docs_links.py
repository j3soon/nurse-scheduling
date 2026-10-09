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

"""Test documentation links across built pages, README reuse, and redirects."""

import tempfile
import unittest
from pathlib import Path

from check_docs_links import check_links


class CheckDocsLinksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("site/index.html", '<h1 id="intro">Home</h1>')
        self.write("netlify.toml", "")
        for name in [
            "README.md",
            "core/README.md",
            "web-frontend/README.md",
            "docker/README.md",
            "docs/README.md",
        ]:
            self.write(name, "")
        (self.root / "docs/content").mkdir()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_relative_pages_assets_and_encoded_fragments(self):
        self.write(
            "site/index.html",
            '<a href="page/#%63hapter">Read</a><img src="assets/example.png">',
        )
        self.write("site/page/index.html", '<h1 id="chapter">Chapter</h1>')
        asset = self.write("site/assets/example.png", "image")
        self.assertEqual(check_links(self.root), [])
        asset.unlink()
        self.assertTrue(
            any(
                "missing built target /docs/assets/example.png" in error
                for error in check_links(self.root)
            )
        )

    def test_stable_and_development_urls_check_fragments(self):
        self.write(
            "README.md",
            "https://nursescheduling.org/docs/#intro\nhttps://dev.nursescheduling.org/docs#intro\n",
        )
        self.assertEqual(check_links(self.root), [])
        self.write(
            "README.md",
            "https://nursescheduling.org/docs/#missing\nhttps://dev.nursescheduling.org/docs#missing\n",
        )
        self.assertEqual(len(check_links(self.root)), 2)

    def test_relative_links_cannot_leave_the_docs_root(self):
        page = "site/developer-guide/containers/index.html"
        self.write(page, '<a href="/experimental-ai/">Open the app</a>')
        self.assertEqual(check_links(self.root), [])
        self.write(
            page,
            '<a href="../../../docker/nginx.backend.conf">Configuration</a>',
        )
        self.assertEqual(
            check_links(self.root),
            [f"{page}: relative link leaves docs: ../../../docker/nginx.backend.conf"],
        )

    def test_redirects_preserve_legacy_fragments(self):
        self.write("README.md", "https://nursescheduling.org/docs/old/#legacy")
        self.write(
            "netlify.toml",
            '[[redirects]]\nfrom = "/docs/old/*"\nto = "/docs/new/:splat"\nstatus = 301\n',
        )
        self.write(
            "site/new/index.html",
            '<span id="legacy"></span><h1 id="current">Current</h1>',
        )
        self.assertEqual(check_links(self.root), [])
        self.write("site/new/index.html", '<h1 id="current">Current</h1>')
        self.assertTrue(
            any("missing anchor" in error for error in check_links(self.root))
        )

    def test_missing_redirect_targets_fail_without_inbound_links(self):
        self.write(
            "netlify.toml",
            '[[redirects]]\nfrom = "/docs/old/*"\nto = "/docs/missing/:splat"\nstatus = 301\n',
        )
        self.assertTrue(
            any(
                "missing built target /docs/missing/" in error
                for error in check_links(self.root)
            )
        )

    def test_repository_readme_links_use_the_built_symlink_page(self):
        self.write(
            "README.md",
            "https://github.com/j3soon/nurse-scheduling/blob/dev/core/README.md#install",
        )
        path = self.root / "docs/content/core.md"
        path.symlink_to(self.root / "core/README.md")
        self.write("site/core/index.html", '<h1 id="install">Install</h1>')
        self.assertEqual(check_links(self.root), [])
        self.write("site/core/index.html", '<h1 id="renamed">Renamed</h1>')
        self.assertTrue(
            any("missing anchor" in error for error in check_links(self.root))
        )
        self.write(
            "README.md", "https://github.com/j3soon/nurse-scheduling/blob/dev/absent.md"
        )
        self.assertTrue(
            any("missing repository file" in error for error in check_links(self.root))
        )

    def test_redirect_cycles_are_reported(self):
        self.write(
            "netlify.toml",
            '[[redirects]]\nfrom = "/docs/a/"\nto = "/docs/b/"\n[[redirects]]\nfrom = "/docs/b/"\nto = "/docs/a/"\n',
        )
        self.assertTrue(
            any("redirect cycle" in error for error in check_links(self.root))
        )

    def test_missing_build_is_reported(self):
        (self.root / "site/index.html").unlink()
        self.assertIn("Build the docs", check_links(self.root)[0])
