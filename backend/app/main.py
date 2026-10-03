import logging
from time import perf_counter
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import health, requests, reviews
from app.core.config import get_settings
from app.services.errors import WorkflowError

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.name, version=settings.version)
    application.include_router(health.router)
    application.include_router(requests.router)
    application.include_router(reviews.router)

    @application.exception_handler(WorkflowError)
    async def workflow_error_handler(request: Request, exc: WorkflowError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.middleware("http")
    async def log_request(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error("request_failed")
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        route = request.scope.get("route")
        logger.info("http_request_completed", extra={
            "method": request.method,
            "route": getattr(route, "path", "unmatched"),
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        })
        return response

    @application.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # DB errors can contain SQL, parameters, and credentials. Do not log or echo them.
        logger.warning("database_operation_failed")
        return JSONResponse(status_code=503, content={"detail": "Database operation failed"})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Do not reflect submitted healthcare text in validation errors.
        errors = [
            {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    return application


app = create_app()
