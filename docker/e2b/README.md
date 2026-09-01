# E2B Sandbox Template

This directory defines the reusable E2B Cloud template for the experimental AI
assistant. Each assistant turn starts a fresh sandbox from the prebuilt
template, hydrates `/workspace`, and destroys the sandbox after the turn.

The template uses one vCPU and 512 MiB of memory. It runs as the unprivileged
`user` account and provides Bash, Python, ripgrep, sed, grep, and diff. Runtime
code writes only under `/workspace`. The application hydrates `/reference`
separately so reference material stays synchronized with the backend.

## Build

Set `E2B_API_KEY` and optionally override `E2B_TEMPLATE` in the ignored
repository-root `.env.ai` file. Install the core dependencies, then run from the
repository root:

```sh
source core/.venv/bin/activate
set -a
source .env.ai
set +a
python docker/e2b/build_template.py
```

The default alias is `nurse-scheduling-ai-sandbox`. Rebuild the template only
when its Dockerfile or installed tools change. Normal sandbox launches reuse
the prebuilt template and do not install packages.

The E2B API key belongs only to the trusted application and build processes.
Never copy it, provider credentials, or database credentials into the template
or a sandbox environment. Application-created sandboxes disable outbound
internet access and are killed after one complete user message.
