<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# OpenCC browser converter

`cn2t.js` is the unmodified UMD bundle from `opencc-js` 1.4.2:
https://registry.npmjs.org/opencc-js/-/opencc-js-1.4.2.tgz

Upstream: https://github.com/nk2028/opencc-js/tree/v1.4.2

Shared vendored libraries belong in the repository-root `thirdparty/` directory.
The frontend imports this bundle. Python embeds the same bundle and its license
notices in standalone chat HTML. No CDN or JavaScript package installation is
needed for offline conversion. The converter uses `from: 'cn', to: 'twp'`, which
corresponds to OpenCC `s2twp`.

To update, replace `dist/umd/cn2t.js`, `LICENSE`, and `THIRD_PARTY_LICENSES.md`
from the same published package. Keep the bundle unmodified. Run chat rendering
and export tests, then update the export reference hashes and archive fixture.
`cn2t.d.ts` declares the subset of the upstream API used by this project.
Both backend Docker images copy `thirdparty/opencc/` for offline HTML exports.
