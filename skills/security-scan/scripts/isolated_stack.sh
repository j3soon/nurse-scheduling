#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

# Start or stop a loopback-only copy of the backend services for adversarial checks.
# It never touches a running deployment, Docker, E2B, or a real model provider.
#
#   isolated_stack.sh start [REPO_ROOT]   start services and write stack.env
#   isolated_stack.sh stop [REPO_ROOT]    stop services started by this script
#
# Services, each on a free 127.0.0.1 port:
#   API_OPEN_URL   optimizer API without keys, like an open deployment
#   API_KEYED_URL  optimizer API that requires API_TOKEN
#   AI_URL         AI service that requires AI_TOKEN, using API_OPEN_URL for jobs
#   PROVIDER_URL   stub model provider used by the AI service
# Set JOB_REDIS_URL to back both APIs with Redis instead of process memory.

set -euo pipefail

action="${1:-}"
repo_root="$(cd -- "${2:-$PWD}" && pwd)"
skill_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
state_dir="${SECURITY_SCAN_STATE_DIR:-$repo_root/artifacts/security-scan/stack}"

if [[ ! -d "$repo_root/core/nurse_scheduling" ]]; then
  printf 'error: %s is not the repository root\n' "$repo_root" >&2
  exit 2
fi

stop_stack() {
  local pid_file pid
  for pid_file in "$state_dir"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    pid="$(cat "$pid_file")"
    kill "$pid" 2>/dev/null || true
    # Uvicorn shuts down gracefully, so wait before reusing ports or reporting success.
    for _ in $(seq 1 50); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
  done
}

free_port() {
  python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

wait_ready() {
  local name="$1" url="$2"
  for _ in $(seq 1 100); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done
  printf 'error: %s did not become ready, see %s/%s.log\n' "$name" "$state_dir" "$name" >&2
  stop_stack
  exit 1
}

start_service() {
  local name="$1"
  shift
  ( cd "$repo_root/core" && exec env "$@" ) >"$state_dir/$name.log" 2>&1 &
  echo $! >"$state_dir/$name.pid"
}

case "$action" in
  stop)
    stop_stack
    exit 0
    ;;
  start) ;;
  *)
    printf 'usage: %s start|stop [REPO_ROOT]\n' "$0" >&2
    exit 2
    ;;
esac

mkdir -p "$state_dir"
stop_stack

api_open_port="$(free_port)"
api_keyed_port="$(free_port)"
ai_port="$(free_port)"
provider_port="$(free_port)"
api_token="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
ai_token="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
job_backend=memory
[[ -n "${JOB_REDIS_URL:-}" ]] && job_backend=redis

# Mirror the Compose services, which trust forwarded headers from their proxy. Here the
# scanner is that proxy, so it chooses X-Forwarded-For as NGINX would.
uvicorn_api=(python -m uvicorn nurse_scheduling.serve:app --host 127.0.0.1 --proxy-headers
  --forwarded-allow-ips 127.0.0.1 --no-access-log)
common_env=(DISABLE_SENTRY=1 JOB_BACKEND="$job_backend" JOB_REDIS_URL="${JOB_REDIS_URL:-}"
  OPTIMIZE_MAX_TIMEOUT_SECONDS=60 OPTIMIZE_DEFAULT_TIMEOUT_SECONDS=5)

start_service provider python "$skill_dir/stub_provider.py" --port "$provider_port"
start_service api-open "${common_env[@]}" API_AUTH_REQUIRED=false \
  JOB_REDIS_KEY_PREFIX="security-scan:open:v0" "${uvicorn_api[@]}" --port "$api_open_port"
start_service api-keyed "${common_env[@]}" API_AUTH_REQUIRED=true API_AUTH_TOKEN="$api_token" \
  JOB_REDIS_KEY_PREFIX="security-scan:keyed:v0" "${uvicorn_api[@]}" --port "$api_keyed_port"
start_service ai DISABLE_SENTRY=1 PYTHONPATH="$repo_root/core" \
  AI_AUTH_REQUIRED=true AI_AUTH_TOKEN="$ai_token" AI_COOKIE_SECURE=1 \
  AI_PROVIDER_BASE_URL="http://127.0.0.1:$provider_port/v1" AI_PROVIDER_API_KEY=stub \
  AI_PROVIDER_MODEL=scan-model AI_SANDBOX_BACKEND=e2b E2B_API_KEY=unused \
  AI_OPTIMIZER_BASE_URL="http://127.0.0.1:$api_open_port" \
  python "$skill_dir/serve_ai_isolated.py" --port "$ai_port"

wait_ready provider "http://127.0.0.1:$provider_port/v1/models"
wait_ready api-open "http://127.0.0.1:$api_open_port/ready"
wait_ready api-keyed "http://127.0.0.1:$api_keyed_port/ready"
wait_ready ai "http://127.0.0.1:$ai_port/ready"

cat >"$state_dir/stack.env" <<EOF
API_OPEN_URL=http://127.0.0.1:$api_open_port
API_KEYED_URL=http://127.0.0.1:$api_keyed_port
AI_URL=http://127.0.0.1:$ai_port
PROVIDER_URL=http://127.0.0.1:$provider_port/v1
API_TOKEN=$api_token
AI_TOKEN=$ai_token
JOB_BACKEND=$job_backend
EOF
chmod 600 "$state_dir/stack.env"
printf 'Isolated stack is ready. Settings: %s/stack.env\n' "$state_dir"
