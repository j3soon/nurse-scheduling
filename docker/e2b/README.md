# E2B Sandbox Template

This directory defines the reusable E2B Cloud template for the experimental AI
assistant. Each assistant turn starts a fresh sandbox from the prebuilt
template, hydrates `/workspace`, and destroys the sandbox after the turn.

The template uses one vCPU and 512 MiB of memory. It runs as the unprivileged
`user` account and provides Bash, Python with `ruamel.yaml`, ripgrep, sed, grep,
diff, and the read-only `nsctl` schema helper. Runtime code writes only under
`/workspace`. The application hydrates
`/reference` separately so reference material stays synchronized with the
backend.

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

After each file or command operation, the backend schedules an explicit
warm-memory pause. Immediate follow-up operations cancel a pause that has not
started. Otherwise E2B auto-resumes the same sandbox on the next operation.
Warm-memory pause is intentional. Five fresh disk-only resume trials took 5.95
to 12.62 seconds, with an 8.01-second median.

The timeout is not the hard deadline. E2B 2.46.0 testing showed that
`on_timeout=kill` did not kill a manually paused sandbox. The application turn
deadline always ends with an explicit kill, including failure and cancellation
paths. The live test also verifies that an explicitly killed sandbox cannot be
resumed.

## Test

Most tests use the in-memory fake backend and need no E2B account:

```sh
cd core
pytest -q tests/test_ai_sandbox.py tests/test_ai_sandbox_agent.py \
  tests/test_ai_pi_bash.py tests/test_ai_sandbox_bash.py tests/test_ai_nsctl.py \
  tests/test_ai_sandbox_e2b.py
```

The opt-in cloud lifecycle checks use the prebuilt template, verify timeout
pause, auto-resume, terminal explicit kill, and the observed manually paused
timeout behavior. Every test destroys its sandbox on exit:

```sh
set -a
source .env.ai
set +a
cd core
RUN_E2B_INTEGRATION=1 pytest -q tests/test_ai_sandbox_e2b_live.py
```

`E2BSandboxBackend` is the current cloud adapter. Agent code depends only on
the provider-neutral `SandboxBackend` contract so future self-hosted E2B or
remote gVisor adapters can be added independently.
