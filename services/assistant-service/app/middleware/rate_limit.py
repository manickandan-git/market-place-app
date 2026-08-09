import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings


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
