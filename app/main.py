import re
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

from app.api.routes import (
    anomalies,
    dashboard,
    department_metrics,
    dim_stores,
    insights,
    metrics,
    series,
    store_metrics,
)
from app.core import (
    metrics as _metrics,  # noqa: F401  # register custom counters with the prometheus default registry at startup
)
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.session import get_db

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

# Canonical UUID format (8-4-4-4-12 lowercase hex). The middleware accepts
# incoming X-Request-ID headers only when they match this shape and are at
# most 36 characters; any other value is replaced with a freshly generated
# UUID. Rejected input is never logged or echoed, since it can be attacker-
# controlled and propagating it would amplify the response and pressure
# structlog contextvars on every request.
_REQUEST_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_REQUEST_ID_MAX_LEN = 36


def _validate_request_id(value: str | None) -> str:
    """Return a valid request ID — the incoming value if it is a well-formed
    canonical UUID, a freshly generated UUID otherwise."""
    if value is not None and len(value) <= _REQUEST_ID_MAX_LEN and _REQUEST_ID_RE.match(value):
        return value
    return str(uuid.uuid4())


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Per-request boundary logging with request correlation IDs.

    On entry: validate the incoming X-Request-ID header against the
    canonical UUID format; accept it when well-formed, otherwise generate
    a fresh UUID. Bind the id to structlog contextvars so every log line
    emitted during the request lifetime automatically includes
    request_id=<uuid>.

    On exit: log method, path, status code, and elapsed time as a
    structured event. Echo the request ID on the response's own
    X-Request-ID header. Clear contextvars so the next request starts
    fresh.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = _validate_request_id(request.headers.get("X-Request-ID"))

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
app.include_router(department_metrics.router)
app.include_router(dim_stores.router)


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
        reason=(
            "STORE_METRICS_PATH, ANOMALY_FLAGS_PATH, DEPARTMENT_METRICS_PATH, "
            "and/or DIM_STORES_PATH unset or unreadable"
        ),
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
    Component-level liveness and readiness check.

    The service composes two independent pipelines. The grocery pipeline
    serves canonical parquet data and is the platform-critical path; the
    macro pipeline serves economic series from Postgres. They fail
    independently, so /health reports each one separately.

    Overall status and HTTP code track the grocery pipeline: 200 whenever
    it can serve data, "degraded" when the macro database is unreachable
    but grocery is fine, 503 only when the grocery pipeline itself cannot
    serve data.
    """
    grocery_available = settings.grocery_data_available
    grocery = {
        "status": "healthy" if grocery_available else "unavailable",
        "mode": "online" if settings.grocery_data_source == "live" else "offline",
        "canonical_path": settings.canonical_path,
    }

    try:
        db.execute(text("SELECT 1"))
        macro = {"status": "healthy"}
    except Exception as exc:
        logger.warning(
            "health_macro_db_check_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        macro = {"status": "unavailable", "reason": "database unreachable"}

    if not grocery_available:
        overall_status, http_status = "unhealthy", 503
    elif macro["status"] != "healthy":
        overall_status, http_status = "degraded", 200
    else:
        overall_status, http_status = "healthy", 200

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "version": settings.API_VERSION,
            "grocery_pipeline": grocery,
            "macro_pipeline": macro,
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
