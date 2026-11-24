#!/usr/bin/env bash

set -euo pipefail

# Keep this list aligned with docker/compose.backend*.yml and the Dockerfiles
# selected by their default and staging API_DOCKERFILE settings.
# skills/upgrade-dependencies/scripts/dependency_inventory.py --check rejects
# a tag that differs from those files.
images=(
  "python:3.14-slim"
  "redis:8.10"
  "redis/redisinsight:3.10.1"
  "postgres:18-alpine"
  "dpage/pgadmin4:9.19"
  "nginx:1.31-alpine"
  "cloudflare/cloudflared:latest"
)

for image in "${images[@]}"; do
  docker pull "$image"
done
