"""Tests for ChatRateLimitMiddleware's per-caller keying, particularly the
anonymous-traffic-behind-the-gateway bug from docs/guardrails.md finding E:
without X-Forwarded-For, every signed-out guest proxied through api-gateway
shared one bucket (request.client.host was always the gateway's own
docker-network address)."""

from types import SimpleNamespace

import pytest

from app.middleware.rate_limit import ChatRateLimitMiddleware


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    def __init__(self, headers=None, client_host=None, path="/api/v1/assistant/chat"):
        self.headers = headers or {}
        self.client = FakeClient(client_host) if client_host is not None else None
        self.method = "POST"
        self.url = SimpleNamespace(path=path)


def test_client_key_uses_bearer_token_when_present():
    request = FakeRequest(
        headers={"Authorization": "Bearer abc123"}, client_host="10.0.0.5"
    )
    assert ChatRateLimitMiddleware._client_key(request) == "token:Bearer abc123"


def test_client_key_two_different_tokens_get_different_keys():
    r1 = FakeRequest(headers={"Authorization": "Bearer token-a"})
    r2 = FakeRequest(headers={"Authorization": "Bearer token-b"})
    assert ChatRateLimitMiddleware._client_key(
        r1
    ) != ChatRateLimitMiddleware._client_key(r2)


def test_client_key_prefers_x_forwarded_for_over_request_client_host():
    # api-gateway sets X-Forwarded-For to the real caller's IP;
    # request.client.host would otherwise always be the gateway's own
    # docker-network address for every proxied request (see
    # services/api-gateway/app/services/proxy_service.py).
    request = FakeRequest(
        headers={"X-Forwarded-For": "203.0.113.7"}, client_host="172.24.0.5"
    )
    assert ChatRateLimitMiddleware._client_key(request) == "ip:203.0.113.7"


def test_client_key_two_anonymous_callers_behind_gateway_get_different_keys():
    # The bug this fixes: without X-Forwarded-For, both of these collapse to
    # the same "ip:172.24.0.5" (the gateway's own address) key, sharing one
    # rate-limit bucket across every guest.
    r1 = FakeRequest(
        headers={"X-Forwarded-For": "203.0.113.7"}, client_host="172.24.0.5"
    )
    r2 = FakeRequest(
        headers={"X-Forwarded-For": "203.0.113.8"}, client_host="172.24.0.5"
    )
    assert ChatRateLimitMiddleware._client_key(
        r1
    ) != ChatRateLimitMiddleware._client_key(r2)


def test_client_key_falls_back_to_request_client_host_without_gateway():
    # Direct-to-service testing (no gateway in front) has no
    # X-Forwarded-For to trust, so request.client.host is the best
    # available signal.
    request = FakeRequest(client_host="127.0.0.1")
    assert ChatRateLimitMiddleware._client_key(request) == "ip:127.0.0.1"


def test_client_key_unknown_when_no_client_and_no_token():
    request = FakeRequest()
    assert ChatRateLimitMiddleware._client_key(request) == "ip:unknown"


@pytest.fixture
def middleware():
    mw = ChatRateLimitMiddleware(app=None)
    mw._limit = 1
    return mw


async def _call_next(_request):
    return "ok"


async def test_dispatch_two_anonymous_callers_behind_gateway_have_independent_limits(
    middleware,
):
    r1 = FakeRequest(
        headers={"X-Forwarded-For": "203.0.113.7"}, client_host="172.24.0.5"
    )
    r2 = FakeRequest(
        headers={"X-Forwarded-For": "203.0.113.8"}, client_host="172.24.0.5"
    )

    # Each caller's first request succeeds under a limit of 1/window...
    assert await middleware.dispatch(r1, _call_next) == "ok"
    assert await middleware.dispatch(r2, _call_next) == "ok"
    # ...and r1's second request is throttled without affecting r2, proving
    # they're in separate buckets despite sharing request.client.host.
    result = await middleware.dispatch(r1, _call_next)
    assert result.status_code == 429
