import logging
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.event_logger import log_event

logger = logging.getLogger(__name__)


class ChatRateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limit scoped to POST /assistant/chat.

    In-memory only — correct for the single-worker/single-replica dev
    deployment this service currently runs as. If assistant-service is ever
    scaled to multiple workers or replicas, this needs a shared store
    (Redis) instead, since each process would otherwise enforce its own
    independent limit.

    Keyed by the raw (unverified) bearer token when present, else by client
    IP — this service never verifies JWTs itself (every tool call either
    relays the buyer's token downstream or is an unauthenticated public
    read, see README), so an unverified token string is still enough to
    distinguish one caller from another for throttling purposes.

    Anonymous traffic is keyed by X-Forwarded-For when present, not
    request.client.host directly: every request arrives via api-gateway
    (services/api-gateway/app/services/proxy_service.py), which otherwise
    means request.client.host is always the gateway's own docker-network
    IP — collapsing every signed-out guest into one shared bucket. The
    gateway sets X-Forwarded-For to the real caller's IP for exactly this
    reason. Falling back to request.client.host keeps this middleware
    correct when tested directly against this service (bypassing the
    gateway), where there's no X-Forwarded-For to trust.
    """

    def __init__(self, app):
        super().__init__(app)
        settings = get_settings()
        self._limit = settings.chat_rate_limit_requests
        self._window_seconds = settings.chat_rate_limit_window_seconds
        self._path = f"{settings.api_prefix}/assistant/chat"
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _client_key(request) -> str:
        auth = request.headers.get("Authorization")
        if auth:
            return f"token:{auth}"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded}"
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"

    async def dispatch(self, request, call_next):
        if request.method != "POST" or request.url.path != self._path:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - self._window_seconds:
            hits.popleft()

        if len(hits) >= self._limit:
            retry_after = max(1, int(self._window_seconds - (now - hits[0])))
            # CorrelationIdMiddleware sits inside this middleware in the
            # actual stack (Starlette wraps in reverse of add_middleware()
            # call order) and never runs at all for a short-circuited 429
            # (call_next is never invoked) — request.state.request_id
            # wouldn't exist here. Read the incoming header directly instead,
            # same fallback CorrelationIdMiddleware itself uses.
            # key is "token:<raw bearer token>" or "ip:<address>" — only the
            # type prefix is safe to log, never the raw key itself.
            log_event(
                logger,
                "chat_rate_limited",
                key_type=key.split(":", 1)[0],
                retry_after=retry_after,
                request_id=request.headers.get("X-Request-ID"),
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "message": (
                        "Too many chat requests. Please wait before trying again."
                    ),
                },
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
