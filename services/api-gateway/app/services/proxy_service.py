import httpx
from fastapi import Request, Response

from app.config import Settings
from app.exceptions import ServiceError
from app.services.circuit_breaker import CircuitBreaker

# Headers that are per-hop, not end-to-end (RFC 7230 §6.1) — recomputed by
# httpx/the ASGI server on each leg, so forwarding the caller's or the
# upstream's copy verbatim would corrupt the response (stale Content-Length
# after body re-encoding, wrong Host, etc.).
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


class ProxyService:
    """Forwards a request byte-for-byte to a resolved upstream service.

    No retries: several upstream endpoints are non-idempotent (payment
    authorization, order creation) and a blind retry-on-timeout here could
    double-charge or double-create. A caller that wants retry semantics
    should retry itself with an idempotency key, same as calling a service
    directly would require.
    """

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            cooldown_seconds=settings.circuit_breaker_cooldown_seconds,
        )

    async def forward(
        self, request: Request, upstream_base: str, service_key: str
    ) -> Response:
        if self._circuit_breaker.is_open(service_key):
            raise ServiceError(
                503,
                "circuit_open",
                f"{service_key} is temporarily unavailable "
                "(circuit open after repeated failures)",
            )

        target_url = f"{upstream_base}{request.url.path}"
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        headers["X-Request-ID"] = getattr(request.state, "request_id", "") or ""
        # Every proxied request otherwise arrives at the upstream service
        # from this gateway's own docker-network IP, not the real caller's
        # — for assistant-service's anonymous-traffic rate limit
        # (ChatRateLimitMiddleware._client_key()) this collapsed every
        # signed-out guest into one shared bucket. This gateway is the only
        # hop in front of any service, so a single value (not appending to
        # an existing chain) is correct here.
        if request.client:
            headers["X-Forwarded-For"] = request.client.host
        body = await request.body()

        try:
            upstream_response = await self._client.request(
                request.method,
                target_url,
                params=request.url.query or None,
                content=body,
                headers=headers,
                timeout=self._settings.downstream_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            self._circuit_breaker.record_failure(service_key)
            raise ServiceError(
                504, "upstream_timeout", "Upstream service timed out"
            ) from exc
        except httpx.ConnectError as exc:
            self._circuit_breaker.record_failure(service_key)
            raise ServiceError(
                502, "upstream_unavailable", "Upstream service is unavailable"
            ) from exc
        except httpx.TransportError as exc:
            # Anything else transport-level (reset connection, protocol
            # error, DNS failure not surfaced as ConnectError, ...) — same
            # treatment as a plain connect failure.
            self._circuit_breaker.record_failure(service_key)
            raise ServiceError(
                502, "upstream_unavailable", "Upstream service is unavailable"
            ) from exc

        self._circuit_breaker.record_success(service_key)

        response_headers = {
            key: value
            for key, value in upstream_response.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type"),
        )
