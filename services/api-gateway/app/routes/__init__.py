from app.routes.docs import router as docs_router
from app.routes.health import router as health_router
from app.routes.proxy import router as proxy_router

__all__ = ["docs_router", "health_router", "proxy_router"]
