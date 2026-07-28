from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class NotFoundError(Exception):
    pass


class StaleVersionError(Exception):
    pass


class ConflictError(Exception):
    pass


def register_exception_handlers(app: FastAPI) -> None:
    def problem(request: Request, status_code: int, title: str, detail: str, errors=None):
        request_id = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": title,
                "status": status_code,
                "detail": detail,
                "instance": str(request.url.path),
                "request_id": request_id,
                "errors": errors or [],
            },
        )

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return problem(request, 404, "Not Found", str(exc))

    @app.exception_handler(StaleVersionError)
    async def stale(request: Request, exc: StaleVersionError):
        return problem(request, 412, "Precondition Failed", str(exc))

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError):
        return problem(request, 409, "Conflict", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        errors = [
            {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]
        return problem(request, 422, "Validation Error", "Request validation failed", errors)

    @app.exception_handler(HTTPException)
    async def http(request: Request, exc: HTTPException):
        return problem(request, exc.status_code, "HTTP Error", str(exc.detail))
