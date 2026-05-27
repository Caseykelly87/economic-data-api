from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    # API
    API_ENV: str = "development"
    API_TITLE: str = "Economic Data API"
    API_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    # Comma-separated list of allowed origins, or "*" for any (development only).
    # Production example: "https://app.example.com,https://admin.example.com"
    CORS_ORIGINS: str = "*"

    # Grocery data sources
    STORE_METRICS_PATH: str | None = None
    ANOMALY_FLAGS_PATH: str | None = None
    DEPARTMENT_METRICS_PATH: str | None = None
    DIM_STORES_PATH: str | None = None
    GROCERY_FIXTURES_DIR: str = "app/fixtures"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def resolved_store_metrics_path(self) -> str:
        """Live STORE_METRICS_PATH if it points at a readable file, else
        the bundled fixture. Used by services and the /health probe."""
        if self.STORE_METRICS_PATH and Path(self.STORE_METRICS_PATH).is_file():
            return self.STORE_METRICS_PATH
        return f"{self.GROCERY_FIXTURES_DIR}/store_daily_metrics.parquet"

    @property
    def resolved_anomaly_flags_path(self) -> str:
        """Live ANOMALY_FLAGS_PATH if it points at a readable file, else
        the bundled fixture."""
        if self.ANOMALY_FLAGS_PATH and Path(self.ANOMALY_FLAGS_PATH).is_file():
            return self.ANOMALY_FLAGS_PATH
        return f"{self.GROCERY_FIXTURES_DIR}/anomaly_flags.parquet"

    @property
    def resolved_department_metrics_path(self) -> str:
        """Live DEPARTMENT_METRICS_PATH if it points at a readable file, else
        the bundled fixture."""
        if self.DEPARTMENT_METRICS_PATH and Path(self.DEPARTMENT_METRICS_PATH).is_file():
            return self.DEPARTMENT_METRICS_PATH
        return f"{self.GROCERY_FIXTURES_DIR}/department_daily_metrics.parquet"

    @property
    def resolved_dim_stores_path(self) -> str:
        """Live DIM_STORES_PATH if it points at a readable file, else
        the bundled fixture."""
        if self.DIM_STORES_PATH and Path(self.DIM_STORES_PATH).is_file():
            return self.DIM_STORES_PATH
        return f"{self.GROCERY_FIXTURES_DIR}/dim_stores.parquet"

    @property
    def grocery_data_source(self) -> str:
        """'live' if all four configured paths exist, 'fixtures' otherwise.
        Reported by /health and logged at startup."""
        live_metrics = bool(self.STORE_METRICS_PATH) and Path(self.STORE_METRICS_PATH).is_file()
        live_flags = bool(self.ANOMALY_FLAGS_PATH) and Path(self.ANOMALY_FLAGS_PATH).is_file()
        live_departments = bool(self.DEPARTMENT_METRICS_PATH) and Path(self.DEPARTMENT_METRICS_PATH).is_file()
        live_dim_stores = bool(self.DIM_STORES_PATH) and Path(self.DIM_STORES_PATH).is_file()
        return "live" if (live_metrics and live_flags and live_departments and live_dim_stores) else "fixtures"

    def _resolved_paths_exist(self) -> tuple[bool, bool, bool, bool]:
        """Whether each of (store_metrics, anomaly_flags,
        department_metrics, dim_stores) resolved paths point at a
        readable file. Centralized so /health's grocery_data_available
        check is a single pass over the four resolved paths rather than
        four scattered ``Path(...).is_file()`` calls. Note that
        ``grocery_data_source`` checks the configured live paths, not the
        resolved paths, so it does not share this helper — the semantics
        intentionally differ."""
        return (
            Path(self.resolved_store_metrics_path).is_file(),
            Path(self.resolved_anomaly_flags_path).is_file(),
            Path(self.resolved_department_metrics_path).is_file(),
            Path(self.resolved_dim_stores_path).is_file(),
        )

    @property
    def grocery_data_available(self) -> bool:
        """True when all four grocery parquet files resolve to readable
        files — configured live paths where set, bundled fixtures
        otherwise. The grocery pipeline can serve data whenever this holds.
        Reported by /health."""
        return all(self._resolved_paths_exist())

    @property
    def canonical_path(self) -> str:
        """Directory the grocery parquet files are served from: the live
        canonical directory in online mode, the bundled fixtures directory
        otherwise. Reported by /health."""
        return str(Path(self.resolved_store_metrics_path).parent)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings instance, constructed lazily on
    first call and memoized thereafter."""
    return Settings()


def __getattr__(name: str):
    """Module-level shim so ``from app.core.config import settings``
    continues to work after the move to lazy instantiation. Python invokes
    this when a module attribute is not found by normal lookup; here it
    resolves ``settings`` to the cached Settings instance on first
    access."""
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
