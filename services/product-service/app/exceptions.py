from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class ServiceError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or []


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error_handler(
        request: Request,
        exc: ServiceError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request,
        _exc: IntegrityError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error_code": "resource_conflict",
                "message": "A resource with the same unique value already exists",
                "details": [],
                "request_id": getattr(request.state, "request_id", None),
            },
        )

