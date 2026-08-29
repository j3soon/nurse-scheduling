#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="${BENCHMARK_IMAGE:-j3soon/nurse-scheduling:dev}"
app_version="$(git -C "$repository_root" describe --tags --always --dirty 2>/dev/null || echo "v0.0.0-unknown")"

mkdir -p "$repository_root/artifacts"

if ! docker image inspect "$image_name" >/dev/null 2>&1; then
  echo "Docker image '$image_name' does not exist." >&2
  echo "Build the existing development image or set BENCHMARK_IMAGE to a compatible local image:" >&2
  echo "  docker build -f docker/Dockerfile -t j3soon/nurse-scheduling:dev ." >&2
  exit 1
fi

echo "Reusing Docker image $image_name"
docker run --rm --init \
  --user "$(id -u):$(id -g)" \
  --env "BENCHMARK_APP_VERSION=$app_version" \
  --env "BENCHMARK_ARTIFACT_ROOT=/artifacts" \
  --volume "$repository_root:/workspace:ro" \
  --volume "$repository_root/artifacts:/artifacts" \
  --workdir /workspace/core \
  --entrypoint python \
  "$image_name" -m tests.real.performance_benchmark "$@"
