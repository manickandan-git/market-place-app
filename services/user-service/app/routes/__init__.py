from app.routes.addresses import router as addresses_router
from app.routes.health import router as health_router
from app.routes.preferences import router as preferences_router
from app.routes.privacy import router as privacy_router
from app.routes.profiles import router as profiles_router

__all__ = [
    "addresses_router",
    "health_router",
    "preferences_router",
    "privacy_router",
    "profiles_router",
]
