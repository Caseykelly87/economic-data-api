import logging
import time
import uuid

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core import metrics as _metrics  # noqa: F401  # register custom counters with the prometheus default registry at startup
from app.db.session import get_db
from app.api.routes import series, metrics, insights, store_metrics, anomalies, dashboard

# Configure logging before the app object is used by anything else.
configure_logging(settings.LOG_LEVEL)

logger = structlog.get_logger(__name__)
request_logger = structlog.get_logger("api.requests")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Per-request boundary logging with request correlation IDs.

    On entry: generate a UUID for the request (or accept one from the
    incoming X-Request-ID header if present) and bind it to structlog
    contextvars so every log line emitted during the request lifetime
    automatically includes request_id=<uuid>.

    On exit: log method, path, status code, and elapsed time as a
    structured event. Echo the request ID on the response's own
    X-Request-ID header. Clear contextvars so the next request starts
    fresh.
    """

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming if incoming else str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

        request_logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 1),
        )

        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()
        return response


app.add_middleware(RequestLoggingMiddleware)

# CORSMiddleware must be added after other middleware so it runs outermost.
# Controlled by CORS_ORIGINS in .env — use "*" for local dev, explicit
# origins in staging/production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,   # no cookies or auth headers yet
    allow_methods=["GET"],     # read-only API
    allow_headers=["*"],
)

# Auto-instrument HTTP request metrics and expose /metrics. Must be
# called after middleware setup; the instrumentator hooks into the
# FastAPI dispatch chain at this point.
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(series.router)
app.include_router(metrics.router)
app.include_router(insights.router)
app.include_router(store_metrics.router)
app.include_router(anomalies.router)
app.include_router(dashboard.router)


# ---------------------------------------------------------------------------
# Startup signaling
# ---------------------------------------------------------------------------
# Make demo-vs-live data source visible the moment the api boots, so a
# misconfigured deployment shows up in the logs rather than silently
# serving fixture data.
if settings.grocery_data_source == "fixtures":
    logger.warning(
        "grocery_data_source_fallback",
        data_source="fixtures",
        fixtures_dir=str(settings.GROCERY_FIXTURES_DIR),
        reason="STORE_METRICS_PATH, ANOMALY_FLAGS_PATH, and/or DEPARTMENT_METRICS_PATH unset or unreadable",
    )
else:
    logger.info(
        "grocery_data_source_live",
        data_source="live",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
def health_check(db: Session = Depends(get_db)):
    """
    Liveness + readiness check.

    Returns 200 when the API and database are both reachable.
    Returns 503 when the database cannot be reached, so load balancers and
    orchestrators can route traffic away from unhealthy instances.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
        http_status = 200
        api_status = "ok"
    except Exception as exc:
        logger.warning(
            "health_db_check_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        db_status = "unavailable"
        http_status = 503
        api_status = "degraded"

    return JSONResponse(
        status_code=http_status,
        content={
            "status": api_status,
            "version": settings.API_VERSION,
            "db": db_status,
            "data_source": settings.grocery_data_source,
        },
    )


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        method=request.method,
        path=str(request.url.path),
        error=str(exc),
        error_type=type(exc).__name__,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )
