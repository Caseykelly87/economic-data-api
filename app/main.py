from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": settings.API_VERSION}
