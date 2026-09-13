"""Check provider authentication before an AI evaluation provisions sandboxes."""

import ipaddress
import os
import sys
from dataclasses import dataclass

import httpx


class ProviderPreflightError(RuntimeError):
    """The provider cannot authenticate or accept evaluation traffic."""


@dataclass(frozen=True)
class ProviderPreflightResult:
    status_code: int
    conclusive: bool


def check_provider_auth(
    base_url: str,
    api_key: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProviderPreflightResult:
    """Probe the conventional models endpoint without sending a model request."""
    try:
        provider_url = httpx.URL(base_url)
    except httpx.InvalidURL as exc:
        raise ProviderPreflightError("AI_PROVIDER_BASE_URL is not a valid URL.") from exc
    host = provider_url.host
    try:
        is_loopback = host == "localhost" or (host is not None and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        is_loopback = False
    if provider_url.scheme != "https" and not (provider_url.scheme == "http" and is_loopback):
        raise ProviderPreflightError("AI_PROVIDER_BASE_URL must use HTTPS unless it targets loopback.")
    headers = {} if provider_url.scheme == "http" else {"Authorization": f"Bearer {api_key}"}
    try:
        with httpx.Client(transport=transport, timeout=10.0) as client:
            response = client.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise ProviderPreflightError("The AI provider is unreachable during authentication preflight.") from exc

    if response.status_code in {401, 403}:
        raise ProviderPreflightError(f"The AI provider rejected authentication with HTTP {response.status_code}.")
    if 200 <= response.status_code < 300:
        return ProviderPreflightResult(response.status_code, True)
    if response.status_code == 404:
        return ProviderPreflightResult(response.status_code, False)
    raise ProviderPreflightError(f"The AI provider preflight returned HTTP {response.status_code}.")


def main() -> int:
    base_url = os.getenv("AI_PROVIDER_BASE_URL", "").strip()
    api_key = os.getenv("AI_PROVIDER_API_KEY", "").strip()
    if not base_url or not api_key:
        print("Error: AI_PROVIDER_BASE_URL and AI_PROVIDER_API_KEY are required.", file=sys.stderr)
        return 1
    try:
        result = check_provider_auth(base_url, api_key)
    except ProviderPreflightError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if result.conclusive:
        print(f"AI provider authentication preflight passed (HTTP {result.status_code}).")
    else:
        print(f"AI provider authentication preflight was inconclusive (HTTP {result.status_code}). Continuing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
