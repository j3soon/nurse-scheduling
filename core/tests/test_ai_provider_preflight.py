"""Tests for the AI evaluation provider preflight."""

import httpx
import pytest

from .ai_eval.provider_preflight import ProviderPreflightError, check_provider_auth


def _transport(status_code: int) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(status_code))


def test_provider_preflight_accepts_authenticated_models_response():
    result = check_provider_auth("https://provider.example/v1/", "secret", transport=_transport(200))

    assert result.status_code == 200
    assert result.conclusive


@pytest.mark.parametrize("status_code", [401, 403])
def test_provider_preflight_rejects_authentication_failures(status_code: int):
    with pytest.raises(ProviderPreflightError, match=rf"rejected authentication with HTTP {status_code}"):
        check_provider_auth("https://provider.example/v1", "secret", transport=_transport(status_code))


def test_provider_preflight_allows_an_unsupported_models_endpoint():
    result = check_provider_auth("https://provider.example/v1", "secret", transport=_transport(404))

    assert result.status_code == 404
    assert not result.conclusive


def test_provider_preflight_rejects_provider_outages():
    with pytest.raises(ProviderPreflightError, match="returned HTTP 503"):
        check_provider_auth("https://provider.example/v1", "secret", transport=_transport(503))


def test_provider_preflight_does_not_expose_the_api_key_on_network_failure():
    secret = "do-not-log-this"

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(ProviderPreflightError) as raised:
        check_provider_auth("https://provider.example/v1", secret, transport=httpx.MockTransport(fail))
    assert secret not in str(raised.value)
