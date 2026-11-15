# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

"""Check that corruption fails locally and against an independent package."""

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from check_vendor import check_vendor, main


class CheckVendorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vendor = self.root / "thirdparty" / "opencc"
        self.vendor.mkdir(parents=True)
        contents = {
            "cn2t.js": b"convert();\n",
            "LICENSE": b"MIT\n",
            "THIRD_PARTY_LICENSES.md": b"Dictionary notices\n",
        }
        self.manifest = {"url": "https://example.invalid/opencc.tgz", "files": {}}
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as package:
            for name, data in contents.items():
                member = tarfile.TarInfo("package/" + name)
                member.size = len(data)
                package.addfile(member, io.BytesIO(data))
                (self.vendor / name).write_bytes(data)
                self.manifest["files"][name] = {
                    "path": member.name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
        self.archive = buffer.getvalue()
        self.manifest["sha256"] = hashlib.sha256(self.archive).hexdigest()
        self.save_manifest()
        download = patch("check_vendor.urlopen")
        self.download = download.start()
        self.addCleanup(download.stop)
        self.download.return_value = io.BytesIO(self.archive)

    def save_manifest(self):
        (self.vendor / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def test_offline_checks_never_download(self):
        self.assertEqual(check_vendor(self.root), [])
        self.download.assert_not_called()

    def test_changed_or_missing_local_file_fails_before_download(self):
        (self.vendor / "cn2t.js").write_bytes(b"changed\n")
        (self.vendor / "LICENSE").unlink()
        errors = check_vendor(self.root, upstream=True)
        self.assertEqual(len(errors), 2)
        self.assertIn("cn2t.js: local SHA-256", errors[0])
        self.assertIn("LICENSE:", errors[1])
        self.download.assert_not_called()

    def test_matching_package_passes(self):
        self.assertEqual(check_vendor(self.root, upstream=True), [])
        self.download.assert_called_once_with(self.manifest["url"], timeout=30)

    def test_omitted_manifest_entry_fails(self):
        del self.manifest["files"]["cn2t.js"]
        self.save_manifest()
        self.assertEqual(
            check_vendor(self.root), ["manifest.json: missing pinned files: cn2t.js"]
        )

    def test_changed_archive_fails(self):
        self.download.return_value = io.BytesIO(self.archive + b"changed")
        errors = check_vendor(self.root, upstream=True)
        self.assertIn("archive SHA-256", errors[0])

    def test_changing_local_file_and_hash_still_fails_upstream(self):
        data = b"modified locally\n"
        (self.vendor / "cn2t.js").write_bytes(data)
        self.manifest["files"]["cn2t.js"]["sha256"] = hashlib.sha256(data).hexdigest()
        self.save_manifest()
        self.assertEqual(check_vendor(self.root), [])
        errors = check_vendor(self.root, upstream=True)
        self.assertEqual(
            errors, ["cn2t.js: upstream SHA-256 differs from the manifest"]
        )

    def test_missing_upstream_member_fails(self):
        self.manifest["files"]["cn2t.js"]["path"] = "package/missing.js"
        self.save_manifest()
        errors = check_vendor(self.root, upstream=True)
        self.assertIn("upstream archive is missing package/missing.js", errors[0])

    def test_cli_network_failure_returns_failure(self):
        self.download.side_effect = URLError("upstream unavailable")
        with (
            patch(
                "check_vendor.__file__", str(self.root / "scripts" / "check_vendor.py")
            ),
            patch("sys.argv", ["check_vendor.py", "--upstream"]),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(main(), 1)
        self.assertIn("upstream unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
