"""HTTP transport for the scheduling optimizer."""

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

import asyncio
import ipaddress
import json
import logging
import math
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import ValidationError

from .optimizer import MAX_REJECTION_DETAIL_CHARS, OptimizerArtifact, OptimizerError, OptimizerJobPayload

logger = logging.getLogger("nurse_scheduling.ai.optimizer")


class HttpOptimizerBackend:
    """Call the existing optimizer HTTP API without exposing its credential to the model."""

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        request_timeout_seconds: float,
        max_result_bytes: int,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        endpoint = urlsplit(base_url)
        if auth_token and not (
            endpoint.scheme == "https" or (endpoint.scheme == "http" and _is_trusted_http_host(endpoint.hostname))
        ):
            raise ValueError("A credentialed optimizer endpoint must use HTTPS outside loopback or Docker Compose.")
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
        self._base_url = f"{base_url.rstrip('/')}/"
        self._client = httpx.AsyncClient(headers=headers, timeout=request_timeout_seconds, transport=transport)
        self._max_result_bytes = max_result_bytes
        self._request_timeout_seconds = request_timeout_seconds

    async def submit(self, schedule_yaml: str, timeout_seconds: int | None) -> OptimizerJobPayload:
        fields: dict[str, tuple[None, str]] = {
            "yaml_content": (None, schedule_yaml),
            "prettify": (None, "true"),
        }
        if timeout_seconds is not None:
            fields["timeout"] = (None, str(timeout_seconds))
        payload = await self._request_job("POST", "optimize", files=fields)
        payload.backend = self._backend_info(payload.backend)
        return payload

    def _backend_info(self, body: dict[str, Any] | None) -> dict[str, Any]:
        """Use provenance from the accepting instance's submission response."""
        endpoint = urlsplit(self._base_url)
        host = endpoint.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if endpoint.port is not None:
            host = f"{host}:{endpoint.port}"
        info: dict[str, Any] = {
            "url": f"{endpoint.scheme}://{host}{endpoint.path.rstrip('/')}",
            "request_timeout_seconds": self._request_timeout_seconds,
        }
        if body is None:
            return info
        for key in ("app_version", "api_version", "service_name", "deployment_id", "instance_id"):
            if isinstance(body.get(key), str):
                info[key] = body[key]
        claimed = body.get("claimed_performance")
        if isinstance(claimed, dict):
            score = claimed.get("score")
            if (
                isinstance(score, (int, float))
                and not isinstance(score, bool)
                and math.isfinite(score)
                and score > 0
                and isinstance(claimed.get("app_version"), str)
                and isinstance(claimed.get("measured_at"), str)
            ):
                info["claimed_performance"] = {key: claimed[key] for key in ("score", "app_version", "measured_at")}
        return info

    async def get(self, job_id: str) -> OptimizerJobPayload:
        return await self._request_job("GET", f"optimize/{job_id}")

    async def progress_events(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        """Resume the optimizer event stream without exposing its credential."""
        cursor: str | None = None
        url = urljoin(self._base_url, f"optimize/{job_id}/events")
        while True:
            headers = {"Last-Event-ID": cursor} if cursor is not None else None
            try:
                async with self._client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    event_type = ""
                    data_lines: list[str] = []
                    # Hold the ID until the blank delimiter completes the event. A stream that
                    # drops after the ID would otherwise resume past an event never handled.
                    pending_cursor: str | None = None
                    async for line in response.aiter_lines():
                        if line:
                            if line.startswith("event:"):
                                event_type = line[6:].strip()
                            elif line.startswith("id:"):
                                pending_cursor = line[3:].strip()
                            elif line.startswith("data:"):
                                data_lines.append(line[5:].lstrip())
                            continue
                        if pending_cursor is not None:
                            cursor = pending_cursor
                        if data_lines:
                            try:
                                payload = json.loads("\n".join(data_lines))
                            except ValueError:
                                payload = None
                            if isinstance(payload, dict):
                                if event_type == "job.progressed":
                                    progress = _progress_payload(payload)
                                    if progress is not None:
                                        yield progress
                                elif event_type == "job.state_changed" and payload.get("terminal") is True:
                                    return
                        event_type = ""
                        data_lines = []
                        pending_cursor = None
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {404, 410}:
                    return
                logger.warning("Optimizer progress stream failed job_id=%s status=%s", job_id, exc.response.status_code)
            except httpx.HTTPError as exc:
                logger.warning("Optimizer progress stream disconnected job_id=%s error=%s", job_id, exc)
            await asyncio.sleep(1)

    async def finish_now(self, job_id: str) -> OptimizerJobPayload:
        return await self._request_job("POST", f"optimize/{job_id}/finish-now")

    async def cancel(self, job_id: str) -> OptimizerJobPayload:
        return await self._request_job("POST", f"optimize/{job_id}/cancel")

    async def result_artifact(self, job: OptimizerJobPayload) -> "OptimizerArtifact":
        schedule_link = job.links.get("schedule")
        if not isinstance(schedule_link, str) or not _is_relative_link(schedule_link):
            raise OptimizerError("The optimizer did not provide a result download.")
        try:
            content = bytearray()
            async with self._client.stream("GET", urljoin(self._base_url, schedule_link.lstrip("/"))) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > self._max_result_bytes:
                        raise OptimizerError("The optimizer result exceeded the assistant download limit.")
                    content.extend(chunk)
        except httpx.HTTPError as exc:
            raise OptimizerError("The optimizer result could not be downloaded.") from exc
        if not content:
            raise OptimizerError("The optimizer returned an empty result.")
        return OptimizerArtifact(
            content=bytes(content),
            filename="optimized-schedule.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def delete(self, job_id: str) -> None:
        try:
            response = await self._client.delete(urljoin(self._base_url, f"optimize/{job_id}"))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OptimizerError("The optimizer job could not be deleted.") from exc

    async def _request_job(self, method: str, path: str, **kwargs: Any) -> OptimizerJobPayload:
        try:
            response = await self._client.request(method, urljoin(self._base_url, path), **kwargs)
            response.raise_for_status()
            return OptimizerJobPayload.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            raise OptimizerError(_rejection_reason(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise OptimizerError("The optimizer request failed.") from exc
        except (ValueError, ValidationError) as exc:
            raise OptimizerError("The optimizer returned an invalid job response.") from exc


def _progress_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only finite chart data from a first-party optimizer event."""
    score = payload.get("currentBestScore")
    elapsed = payload.get("elapsedSeconds")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        return None
    progress: dict[str, Any] = {"currentBestScore": score, "elapsedSeconds": elapsed}
    source = payload.get("source")
    if isinstance(source, str):
        progress["source"] = source
    for name in ("solutionIndex", "commentCount"):
        value = payload.get(name)
        if value is None or (isinstance(value, int) and not isinstance(value, bool)):
            progress[name] = value
    return progress


def _rejection_reason(response: httpx.Response) -> str:
    """Relay a first-party optimizer rejection so the model can correct a retryable request."""
    if response.status_code >= 500:
        return "The optimizer request failed."
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, str) or not detail.strip():
        return f"The optimizer rejected the request with status {response.status_code}."
    return f"The optimizer rejected the request: {detail.strip()[:MAX_REJECTION_DETAIL_CHARS]}"


def _is_trusted_http_host(host: str | None) -> bool:
    """Allow cleartext credentials only on loopback or the Compose service name."""
    if host in {"localhost", "api"}:
        return True
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_relative_link(link: str) -> bool:
    """Keep a result download on the configured optimizer, which holds its bearer token."""
    parsed = urlsplit(link)
    return bool(link) and not parsed.scheme and not parsed.netloc
