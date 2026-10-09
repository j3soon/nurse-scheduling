<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Documentation

The documentation uses Zensical. Source pages live under `docs/content/`.
Run these commands from the repository root. They are tested on Linux only.
The developer-guide reproduction pages reuse module READMEs through symlinks.
On Windows, enable Git symlink support or build in Linux or WSL. A checkout that
replaces symlinks with plain text does not render those pages correctly.

```sh
# create virtual environment
uv venv --python 3.12 docs/.venv
# activate virtual environment
source docs/.venv/bin/activate
# install dependencies
uv pip install -r docs/requirements.txt
# preview documentation on the port used by local page-help links
zensical serve
```

For building static site, run:

```sh
python -m unittest discover -s scripts -p test_check_docs_links.py
zensical build --clean --strict
python scripts/check_docs_links.py
```
