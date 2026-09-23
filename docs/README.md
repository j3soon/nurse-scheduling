# Documentation

The documentation is a Zensical site. Pages live under `docs/content/`, and the
site builds to `site/`. The commands below are tested on Linux only.

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

The preview server listens on `127.0.0.1:8003`, the port used by local
page-help links.

For building the static site, run:

```sh
zensical build --clean --strict
```
