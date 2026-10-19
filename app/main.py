"""FastAPI application factory: logging, error handling, router wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import BASE_DIR, LOG_LEVEL
from .database import init_db


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # Keep noisy third-party loggers at INFO.
    logging.getLogger("google").setLevel(logging.WARNING)


ERROR_TITLES = {
    404: "Page not found",
    405: "That action isn't allowed here",
    422: "That didn't go through",
    500: "Something broke",
}


def wants_html(request: Request) -> bool:
    """Browsers navigating pages ask for HTML; API clients don't."""
    return "text/html" in request.headers.get("accept", "")


def error_response(request: Request, status: int, detail) -> Response:
    """JSON for API callers, a styled page for browser navigations."""
    if wants_html(request):
        from .templating import templates

        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "status": status,
                "title": ERROR_TITLES.get(status, "Request failed"),
                "detail": detail,
            },
            status_code=status,
        )
    return JSONResponse(status_code=status, content=jsonable_encoder({"detail": detail}))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logging.getLogger("fitbuddy").info("FitBuddy started — database ready")
    yield


def create_app() -> FastAPI:
    configure_logging()
    # Create tables eagerly so the API works even when the lifespan
    # hook has not run yet (e.g. import-time TestClient usage).
    init_db()

    app = FastAPI(
        title="FitBuddy",
        description="AI-generated 7-day workout plans and nutrition tips.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    from .api import router as api_router
    from .routes import router as pages_router

    app.include_router(api_router)
    app.include_router(pages_router)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or err["loc"][0],
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        logging.getLogger("fitbuddy.validation").warning(
            "Invalid request to %s: %s", request.url.path, errors
        )
        if wants_html(request):
            return error_response(
                request,
                422,
                "One or more values you sent weren't valid. Go back and check the form fields.",
            )
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        return error_response(request, exc.status_code, exc.detail)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logging.getLogger("fitbuddy.errors").exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        return error_response(request, 500, "Internal server error")

    return app


app = create_app()
