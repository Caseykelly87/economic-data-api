import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.session import get_db
from app.api.routes import series, metrics, insights, store_metrics, anomalies, dashboard

# Configure logging before the app object is used by anything else.
configure_logging(settings.LOG_LEVEL)

logger = logging.getLogger(__name__)
request_logger = logging.getLogger("api.requests")

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
    """Log method, path, status code, and elapsed time for every request."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        request_logger.info(
            "%s %s → %d  (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
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
        "STORE_METRICS_PATH and/or ANOMALY_FLAGS_PATH unset or unreadable. "
        "Serving bundled demo fixtures from %s. Set both env vars to use "
        "live ETL output.",
        settings.GROCERY_FIXTURES_DIR,
    )
else:
    logger.info(
        "Grocery data source: live (STORE_METRICS_PATH and ANOMALY_FLAGS_PATH configured)."
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
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
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
        "Unhandled error on %s %s: %s", request.method, request.url, exc, exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )
