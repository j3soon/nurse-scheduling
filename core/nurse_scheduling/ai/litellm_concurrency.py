"""Inspect LiteLLM deployment capacity without sending inference requests."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..sentry import flush_sentry, init_sentry
from ..version import get_app_version

FALLBACK_CONCURRENCY = 4
MAX_EVAL_CONCURRENCY = 20
# LiteLLM persists unchanged health results hourly, rather than after every probe.
HEALTH_MAX_AGE_SECONDS = 7200
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeploymentCapacity:
    id: str
    limit: int | None
    health: str


@dataclass(frozen=True)
class ProviderCapacity:
    model: str
    deployments: tuple[DeploymentCapacity, ...]
    limit: int
    reason: str

    @property
    def configured_limit(self) -> int | None:
        """Total configured capacity, independent of health or current occupancy."""
        if not self.deployments or any(item.limit is None for item in self.deployments):
            return None
        return sum(item.limit for item in self.deployments)

    def select_jobs(self, requested: int | None, attempts: int) -> int:
        """Bound case jobs by provider capacity, sandbox capacity, and queued work."""
        if self.limit == 0:
            raise ValueError("No healthy LiteLLM deployments are available for the selected model.")
        return min(requested or MAX_EVAL_CONCURRENCY, MAX_EVAL_CONCURRENCY, self.limit, max(1, attempts))


def _get_json(client: httpx.Client, url: str, key: str) -> dict | None:
    try:
        response = client.get(url, headers={"Authorization": f"Bearer {key}"})
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        # Keep response bodies, URLs, and credentials out of the JSON capacity report.
        logger.warning("Could not read LiteLLM deployment metadata or cached health", exc_info=True)
        return None


def _health_status(record: object, now: datetime) -> str:
    if not isinstance(record, dict) or record.get("status") not in ("healthy", "unhealthy"):
        return "unknown"
    try:
        checked = datetime.fromisoformat(record["checked_at"].replace("Z", "+00:00"))
        age = (now - checked).total_seconds()
    except (KeyError, TypeError, ValueError, AttributeError):
        return "unknown"
    return record["status"] if 0 <= age <= HEALTH_MAX_AGE_SECONDS else "unknown"


def discover_capacity(
    base_url: str,
    api_key: str,
    model: str,
    *,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> ProviderCapacity:
    """Read per-deployment limits and optional cached health for one model group."""
    with httpx.Client(transport=transport, timeout=10.0) as client:
        metadata = _get_json(client, f"{base_url.rstrip('/')}/model/info", api_key)
        rows = metadata.get("data") if metadata else None
        if not isinstance(rows, list):
            return ProviderCapacity(model, (), FALLBACK_CONCURRENCY, "model metadata unavailable; fallback")
        # Health is a root route, while model info is relative to the /v1 API base.
        health_base = urlsplit(base_url)
        health_path = health_base.path.rstrip("/").removesuffix("/v1") + "/health/latest"
        health_url = urlunsplit(health_base._replace(path=health_path, query="", fragment=""))
        health = _get_json(client, health_url, api_key)
    checks = health.get("latest_health_checks") if health else None
    checks = checks if isinstance(checks, dict) else {}
    now = now or datetime.now(timezone.utc)
    deployments: dict[str, DeploymentCapacity] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("model_name") != model:
            continue
        info, params = row.get("model_info"), row.get("litellm_params")
        info = info if isinstance(info, dict) else {}
        params = params if isinstance(params, dict) else {}
        deployment_id = info.get("id")
        if not isinstance(deployment_id, str) or not deployment_id:
            deployment_id = f"unidentified-{index}"
        limit = params.get("max_parallel_requests")
        limit = limit if type(limit) is int and limit > 0 else None
        deployment = DeploymentCapacity(deployment_id, limit, _health_status(checks.get(deployment_id), now))
        previous = deployments.get(deployment_id)
        if previous is not None and previous != deployment:
            return ProviderCapacity(model, (), FALLBACK_CONCURRENCY, "conflicting deployment metadata; fallback")
        deployments[deployment_id] = deployment
    values = tuple(deployments.values())
    healthy = [item for item in values if item.health == "healthy" and item.limit is not None]
    if not values:
        limit, reason = 0, "no deployments configured for the selected model"
    elif healthy:
        limit = sum(item.limit for item in healthy)
        reason = "sum of confirmed healthy deployment limits"
    elif values and all(item.health == "unhealthy" for item in values):
        limit, reason = 0, "all deployments are unhealthy"
    else:
        limits = [item.limit for item in values if item.limit is not None and item.health != "unhealthy"]
        limit = min([FALLBACK_CONCURRENCY, *limits])
        reason = "health or deployment limits unavailable; conservative fallback"
    return ProviderCapacity(model, values, limit, reason)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.getenv("AI_PROVIDER_BASE_URL", ""), help="OpenAI API base, including /v1"
    )
    parser.add_argument("--model", default=os.getenv("AI_PROVIDER_MODEL", ""))
    args = parser.parse_args(argv)
    key = os.getenv("AI_PROVIDER_API_KEY", "")
    if not args.base_url or not key or not args.model:
        parser.error("AI_PROVIDER_BASE_URL, AI_PROVIDER_API_KEY, and AI_PROVIDER_MODEL are required")
    capacity = discover_capacity(args.base_url, key, args.model)
    print(
        json.dumps(
            {
                **asdict(capacity),
                "configured_limit": capacity.configured_limit,
                "eval_ceiling": min(MAX_EVAL_CONCURRENCY, capacity.limit),
            },
            indent=2,
        )
    )
    return 0 if capacity.deployments and capacity.limit > 0 else 1


def main(argv: list[str] | None = None) -> int:
    init_sentry(get_app_version(), app="ai-litellm-concurrency")
    try:
        return _main(argv)
    finally:
        flush_sentry()


if __name__ == "__main__":
    raise SystemExit(main())
