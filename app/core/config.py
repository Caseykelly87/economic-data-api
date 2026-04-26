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
    def grocery_data_source(self) -> str:
        """'live' if both configured paths exist, 'fixtures' otherwise.
        Reported by /health and logged at startup."""
        live_metrics = bool(self.STORE_METRICS_PATH) and Path(self.STORE_METRICS_PATH).is_file()
        live_flags = bool(self.ANOMALY_FLAGS_PATH) and Path(self.ANOMALY_FLAGS_PATH).is_file()
        return "live" if (live_metrics and live_flags) else "fixtures"


settings = Settings()
