import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.middleware import ChatRateLimitMiddleware, CorrelationIdMiddleware
from app.routes import chat_router, health_router

# Without this, the root logger defaults to WARNING with no handler — every
# logger.info(...) in this service (chat.py's per-request summary,
# loop.py's ServiceError visibility) is silently dropped before it ever
# reaches stdout, even though logger.exception(...) (guardrails #5)
# appeared to work fine (ERROR clears the default WARNING threshold via
# Python's lastResort handler). Plain level=INFO to stdout — same minimal,
# no-new-dependency approach as the rest of this service's logging.
logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(ChatRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(chat_router, prefix=f"{settings.api_prefix}/assistant")
register_exception_handlers(app)