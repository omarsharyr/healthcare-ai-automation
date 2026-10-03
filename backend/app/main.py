import logging
from time import perf_counter
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import agent, analytics, health, requests, reviews
from app.core.config import get_settings
from app.services.errors import WorkflowError
from app.core.correlation import correlation_id, select_correlation_id
from app.core.http_security import LocalWriteBoundary

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.name, version=settings.version)
    application.include_router(health.router)
    application.include_router(requests.router)
    application.include_router(reviews.router)
    application.include_router(agent.router)
    application.include_router(analytics.router)
    application.add_middleware(LocalWriteBoundary)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'backend'])

    @application.get('/', include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse('/docs')

    @application.exception_handler(WorkflowError)
    async def workflow_error_handler(request: Request, exc: WorkflowError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.middleware("http")
    async def log_request(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = perf_counter()
        trace = select_correlation_id(request.headers.get("X-Correlation-ID"))
        token = correlation_id.set(trace)
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.error("request_failed")
                response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
            response.headers["X-Correlation-ID"] = str(trace)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            route = request.scope.get("route")
            logger.info("http_request_completed", extra={
                "method": request.method, "route": getattr(route, "path", "unmatched"),
                "status_code": response.status_code, "correlation_id": str(trace),
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            })
            return response
        finally:
            correlation_id.reset(token)

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
        # Unknown JSON keys can themselves contain patient text. Never reflect them.
        allowed_fields = {"patient_reference", "request_text", "source", "priority", "request_uuid",
                          "review_id", "reviewer_notes", "message", "limit", "offset", "date_from",
                          "date_to", "category", "status"}
        errors = [{"loc": [part if isinstance(part, int) or part in allowed_fields or part in
                            {"body", "path", "query", "header"} else "field" for part in error["loc"]],
                   "msg": "Invalid input", "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    return application


app = create_app()
