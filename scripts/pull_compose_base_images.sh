#!/usr/bin/env bash

set -euo pipefail

# Keep this list aligned with docker/compose.backend*.yml and the Dockerfiles
# selected by their default and staging API_DOCKERFILE settings.
images=(
  "python:3.12-slim"
  "redis:8.8"
  "nginx:1.29-alpine"
  "cloudflare/cloudflared:latest"
)

for image in "${images[@]}"; do
  docker pull "$image"
done
