from fastapi import FastAPI

from app.core.config import settings
from app.api.routes import series, metrics, insights

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(series.router)
app.include_router(metrics.router)
app.include_router(insights.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": settings.API_VERSION}
