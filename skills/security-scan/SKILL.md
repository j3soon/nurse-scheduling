---
name: security-scan
description: Run an adversarial security scan of the backend services against an isolated loopback copy, never the public deployment. Starts the optimizer API and the AI service with a stub model provider and an in-memory sandbox, runs scripted abuse checks, Schemathesis fuzzing, and dependency audits, and reviews code and Compose configuration against a risk checklist. Use when asked for a security scan, penetration test, or adversarial review of nursescheduling.org or the Docker Compose stack. Do not use for a review limited to one diff.
---

# Security Scan

Test a disposable copy of the services at the commit under review. Report
findings with reproduction steps, fix only what the user authorizes, and keep
each fix in its own commit with a regression test.

## Rules

- Never send scan traffic to `nursescheduling.org` or to a running deployment,
  including its containers through the host network. The deployment holds real
  chat history, bills model and E2B usage, and shares one job queue with users.
- Bind every scan service to `127.0.0.1`. Keep `DISABLE_SENTRY=1`, so scan
  traffic never reaches the shared Sentry project.
- A local scan cannot see Cloudflare. Ask the user to review the tunnel's public
  hostnames and the WAF and rate-limit rules in the Cloudflare dashboard.
- Read deployment env files for setting names and non-secret flags only. Mask
  values, for example `sed -E 's/=(.+)/=<set>/'`, and never print a token.
- Store logs and reports under the ignored `artifacts/security-scan/`.

## 1. Review the code and configuration

Read [the review checklist](references/review-checklist.md) and work through it
at `HEAD`. Confirm which commit and env file the deployment uses. A finding that
depends on a deployment setting, such as `API_AUTH_REQUIRED=false`, is
conditional until the user confirms that setting.

## 2. Start the isolated stack

From the repository root:

```bash
bash skills/security-scan/scripts/isolated_stack.sh start "$PWD"
```

The script starts four loopback services on free ports and writes their URLs
and generated tokens to `artifacts/security-scan/stack/stack.env`:

| Name | Service |
| --- | --- |
| `API_OPEN_URL` | Optimizer API without keys, like an open deployment. |
| `API_KEYED_URL` | Optimizer API that requires `API_TOKEN`. |
| `AI_URL` | AI service that requires `AI_TOKEN` and submits jobs to `API_OPEN_URL`. |
| `PROVIDER_URL` | Stub OpenAI-compatible provider that streams one short reply. |

`scripts/serve_ai_isolated.py` reads the AI settings from the environment like
the deployed service and replaces only the E2B sandbox with the in-memory fake.
Services start with a clean environment. They do not inherit deployment keys,
database URLs, or HTTP proxy settings. Both APIs use process memory by default.
To test the Redis store, start a throwaway server and explicitly pass its
loopback URL. Each scan uses a fresh Redis namespace:

```bash
redis-server --bind 127.0.0.1 --port 26391 --save '' --appendonly no --daemonize yes
SECURITY_SCAN_REDIS_URL=redis://127.0.0.1:26391/0 bash skills/security-scan/scripts/isolated_stack.sh start "$PWD"
```

There is no NGINX or Cloudflare in this stack. The services trust forwarded
headers from loopback, so the scanner sets `X-Forwarded-For` as NGINX would.
Check NGINX's header replacement by reading `docker/nginx.backend.conf`.

After changing the scan scripts, run their regression tests:
`python -m unittest discover -s skills/security-scan/scripts -p 'test_*.py'`.

## 3. Run the scripted checks

```bash
python skills/security-scan/scripts/probe.py "$PWD"
```

The probe refuses non-loopback URLs. It derives the route list from the
applications, so a new route is checked for authentication automatically. It
covers authentication, stream tokens, CORS, per-address job limits, body and
YAML bounds, error disclosure, owner cookies, session ownership, and attachment
limits. Each line prints `PASS` or `FAIL`, and the script exits 1 on a failure.
The AI reply check stops at a terminal event or its total wait limit, even when
keepalives continue.
When a scan finds a new issue, add a check here as its regression record.

## 4. Fuzz the HTTP schemas

Set `SCRATCH` to a temporary directory outside the repository. Install the tools
there instead of the system environment:

```bash
python -m pip install --target "$SCRATCH/scan-tools" schemathesis pip-audit
set -a; . artifacts/security-scan/stack/stack.env; set +a
(cd "$SCRATCH" && PYTHONPATH="$SCRATCH/scan-tools" "$SCRATCH/scan-tools/bin/st" run \
  "$API_OPEN_URL/openapi.json" -n 40 --checks all --generation-deterministic)
```

Schemathesis keeps a replay cache in `.schemathesis/` under its working
directory, so run it from `$SCRATCH`.

The keyed services hide their schemas, so generate the AI schema in-process:

```bash
PYTHONPATH=core python - > "$SCRATCH/ai-openapi.json" <<'PY'
import json
from nurse_scheduling.ai.app import create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.sandbox.fake import FakeSandboxFactory
settings = AiSettings(provider_base_url="http://127.0.0.1:9/v1", provider_api_key="x", provider_model="x")
print(json.dumps(create_app(settings=settings, sandbox_factory=FakeSandboxFactory()).openapi()))
PY
(cd "$SCRATCH" && PYTHONPATH="$SCRATCH/scan-tools" "$SCRATCH/scan-tools/bin/st" run "$SCRATCH/ai-openapi.json" \
  --url "$AI_URL" -H "Authorization: Bearer $AI_TOKEN" -n 40 --generation-deterministic \
  -c not_a_server_error,response_schema_conformance,content_type_conformance)
```

Treat every 5xx as a finding. Undocumented 4xx codes and `Allow` header
mismatches are documentation gaps.

## 5. Audit dependencies

`core/requirements.txt` leaves most packages unpinned, so a deployed image has
the versions available on its build date. Audit both a fresh resolution and the
installed development versions, which approximate an older image:

```bash
python -m pip install -q --dry-run --ignore-installed -r core/requirements.txt --report "$SCRATCH/fresh.json"
python -c 'import json, sys
for item in json.load(open(sys.argv[1]))["install"]:
    print(item["metadata"]["name"] + "==" + item["metadata"]["version"])' "$SCRATCH/fresh.json" >"$SCRATCH/fresh-pins.txt"
python -m pip freeze | grep -v '^-e\|@ file' >"$SCRATCH/dev-pins.txt"
for pins in fresh-pins dev-pins; do
  PYTHONPATH="$SCRATCH/scan-tools" python -m pip_audit -r "$SCRATCH/$pins.txt" --no-deps --disable-pip
done
```

`pip-audit` exits 1 when it finds an advisory. For the frontend, run
`bun audit` in `web-frontend/`. The site is a static
export (`output: "export"`), so Next.js server advisories do not reach
production. Separate packages under `dependencies` in `package.json` from
build and test tooling, and report the shipped ones first.

## 6. Stop and report

```bash
bash skills/security-scan/scripts/isolated_stack.sh stop "$PWD"
```

Stop any throwaway Redis server. Report findings first, ranked by severity,
each with a reproduction and the condition it depends on. Then list what held
up and what the scan did not cover. Typical gaps are Cloudflare and NGINX
behavior, AI history restore, which needs PostgreSQL (see
`scripts/test_ai_postgres.sh`), and real E2B sandbox isolation, which is
reviewed from code only.
