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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
