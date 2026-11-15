#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

"""Verify vendored OpenCC bytes offline or against the pinned npm package."""

import argparse
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def check_vendor(root: Path, *, upstream: bool = False) -> list[str]:
    vendor = root / "thirdparty" / "opencc"
    manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    missing = {"cn2t.js", "LICENSE", "THIRD_PARTY_LICENSES.md"} - files.keys()
    if missing:
        return [f"manifest.json: missing pinned files: {', '.join(sorted(missing))}"]
    errors = []
    for name, entry in files.items():
        try:
            data = (vendor / name).read_bytes()
        except OSError as error:
            errors.append(f"{name}: {error}")
            continue
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            errors.append(f"{name}: local SHA-256 differs from the manifest")
    if errors or not upstream:
        return errors

    with urlopen(manifest["url"], timeout=30) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != manifest["sha256"]:
        return [f"{manifest['url']}: archive SHA-256 differs from the manifest"]
    # Read individual members without extracting any paths to the filesystem.
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        for name, entry in files.items():
            try:
                member = package.getmember(entry["path"])
            except KeyError:
                errors.append(f"{name}: upstream archive is missing {entry['path']}")
                continue
            if not member.isfile():
                errors.append(f"{name}: upstream archive member is not a regular file")
                continue
            with package.extractfile(member) as source:
                if hashlib.sha256(source.read()).hexdigest() != entry["sha256"]:
                    errors.append(f"{name}: upstream SHA-256 differs from the manifest")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream",
        action="store_true",
        help="also download and verify the pinned npm archive",
    )
    args = parser.parse_args()
    try:
        errors = check_vendor(
            Path(__file__).resolve().parents[1], upstream=args.upstream
        )
    except (OSError, URLError, ValueError, KeyError, tarfile.TarError) as error:
        errors = [str(error)]
    if errors:
        print("Vendor integrity check failed:", *errors, sep="\n", file=sys.stderr)
        return 1
    mode = "local and upstream" if args.upstream else "local"
    print(f"OpenCC {mode} integrity checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
