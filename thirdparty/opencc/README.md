<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# OpenCC browser converter

`cn2t.js` is the unmodified UMD bundle from `opencc-js` 1.4.2:
https://registry.npmjs.org/opencc-js/-/opencc-js-1.4.2.tgz

Upstream commit for v1.4.2:
https://github.com/nk2028/opencc-js/tree/ba20c6eda99e7ec385bcf706da2776372675b898

Shared vendored libraries belong in the repository-root `thirdparty/` directory.
The frontend imports this bundle. Python embeds the same bundle and its license
notices in standalone chat HTML. No CDN or JavaScript package installation is
needed for offline conversion. The converter uses `from: 'cn', to: 'twp'`, which
corresponds to OpenCC `s2twp`.

`cn2t.d.ts` declares the subset of the upstream API used by this project.
Both backend Docker images copy `thirdparty/opencc/` for offline HTML exports.

## Integrity checks

`manifest.json` pins the npm archive URL and SHA-256, the upstream path of each
vendored file, and each file's SHA-256. It covers the unmodified bundle and both
license files. `cn2t.d.ts`, this README, and the integrity metadata are maintained
locally. `.gitattributes` preserves upstream bytes on every platform.

Run from the repository root with Python. No extra packages are needed:

```sh
python scripts/check_vendor.py
python scripts/check_vendor.py --upstream
python -m unittest discover -s scripts -p test_check_vendor.py
```

The default check reads only local files. `--upstream` also downloads the pinned
npm archive, checks its SHA-256, and compares the vendored files with its members.
The Check Vendor Integrity workflow runs both checks on every push and pull
request. It can also run manually. Network failures fail the upstream step.
The checker never changes files or hashes.

To upgrade, review the upstream release and published npm package. Replace
`dist/umd/cn2t.js`, `LICENSE`, and `THIRD_PARTY_LICENSES.md` from that package.
Update the version, archive URL, archive hash, file hashes, and upstream commit
reference together. Run both integrity checks and the chat rendering and export
tests, then update the export reference hashes and archive fixture. Do not change
a hash only to silence a failed check. These checks detect byte changes. They do
not establish that upstream code is safe.
